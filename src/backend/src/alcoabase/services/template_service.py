"""Template service for creating and managing report templates.

Provides template lifecycle management including creation with UUID
generation, Field-UUID assignment, immutability enforcement after
ReadOnly status, and retrieval operations.

References:
    - Design doc Section 4: Template Service
    - Requirements 3: Template creation, Field-UUID assignment, immutability
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alcoabase.models.template import Template, TemplateField
from alcoabase.services.uuid_service import UUIDService


class TemplateService:
    """Service for template CRUD operations and immutability enforcement.

    Coordinates between PostgreSQL (metadata) and the UUID service to
    provide transactional template management with Field-UUID uniqueness
    validation and ReadOnly immutability enforcement.

    Attributes:
        _uuid_service: UUIDService instance for UUID generation.
    """

    def __init__(self, uuid_service: UUIDService | None = None) -> None:
        """Initialize the template service.

        Args:
            uuid_service: Optional UUIDService instance (creates default if None).
        """
        self._uuid_service = uuid_service or UUIDService()

    async def create_template(
        self,
        session: AsyncSession,
        name: str,
        json_schema: dict,
        user_id: int,
    ) -> Template:
        """Create a new template with Document-UUID and Field-UUIDs.

        Generates a Document-UUID for the template, assigns a unique
        Field-UUID to each field in the JSON schema, validates Field-UUID
        uniqueness within the template, and sets status to ReadOnly.

        Args:
            session: Active async database session.
            name: Template name.
            json_schema: Template schema dict with format:
                {"fields": [{"label": "...", "type": "Text|Float|Integer|Date|Boolean"}]}
            user_id: ID of the creating user.

        Returns:
            The created Template instance with fields loaded.

        Raises:
            ValueError: If Field-UUID uniqueness validation fails or
                json_schema format is invalid.
        """
        # Validate json_schema structure
        if not isinstance(json_schema, dict) or "fields" not in json_schema:
            raise ValueError("json_schema must contain a 'fields' key")

        fields_data = json_schema.get("fields", [])
        if not isinstance(fields_data, list) or len(fields_data) == 0:
            raise ValueError("json_schema 'fields' must be a non-empty list")

        # Generate Document-UUID for the template
        document_uuid = await self._uuid_service.generate_document_uuid(session)

        # Generate Field-UUIDs for all fields
        field_uuids: list[str] = []
        for _ in fields_data:
            field_uuid = self._uuid_service.generate_field_uuid()
            field_uuids.append(field_uuid)

        # Validate Field-UUID uniqueness within the template
        if len(set(field_uuids)) != len(field_uuids):
            raise ValueError(
                "Field-UUID uniqueness violation: duplicate Field-UUIDs generated"
            )

        # Create template record with ReadOnly status
        template = Template(
            document_uuid=document_uuid,
            name=name,
            json_schema=json_schema,
            status="ReadOnly",
            created_by=user_id,
        )
        session.add(template)
        await session.flush()

        # Create TemplateField records
        for order, (field_data, field_uuid) in enumerate(
            zip(fields_data, field_uuids, strict=True)
        ):
            field = TemplateField(
                template_id=template.id,
                field_uuid=field_uuid,
                field_type=field_data.get("type", "Text"),
                field_label=field_data.get("label", ""),
                field_order=order,
            )
            session.add(field)

        await session.flush()

        # Reload template with fields relationship
        result = await session.execute(
            select(Template)
            .where(Template.id == template.id)
            .options(selectinload(Template.fields))
        )
        return result.scalar_one()

    async def update_template(
        self,
        session: AsyncSession,
        document_uuid: str,
        name: str | None = None,
        json_schema: dict | None = None,
    ) -> Template:
        """Update a template, rejecting modifications to ReadOnly templates.

        Args:
            session: Active async database session.
            document_uuid: The Document-UUID of the template to update.
            name: Optional new template name.
            json_schema: Optional new JSON schema.

        Returns:
            The updated Template instance.

        Raises:
            HTTPException: 400 if template is ReadOnly, 404 if not found.
        """
        result = await session.execute(
            select(Template)
            .where(Template.document_uuid == document_uuid)
            .options(selectinload(Template.fields))
        )
        template = result.scalar_one_or_none()

        if template is None:
            raise HTTPException(
                status_code=404,
                detail=f"Template not found: {document_uuid}",
            )

        if template.status == "ReadOnly":
            raise HTTPException(
                status_code=400,
                detail="Cannot modify a ReadOnly template. Templates are immutable after creation.",
            )

        # Apply updates (only reachable for Draft templates)
        if name is not None:
            template.name = name
        if json_schema is not None:
            template.json_schema = json_schema

        await session.flush()
        return template

    async def get_template(
        self, session: AsyncSession, document_uuid: str
    ) -> Template | None:
        """Retrieve a template by its Document-UUID.

        Args:
            session: Active async database session.
            document_uuid: The Document-UUID to look up.

        Returns:
            The Template instance with fields loaded, or None.
        """
        result = await session.execute(
            select(Template)
            .where(Template.document_uuid == document_uuid)
            .options(selectinload(Template.fields))
        )
        return result.scalar_one_or_none()

    async def list_templates(
        self, session: AsyncSession
    ) -> list[Template]:
        """List all templates.

        Args:
            session: Active async database session.

        Returns:
            List of all Template instances with fields loaded.
        """
        result = await session.execute(
            select(Template).options(selectinload(Template.fields))
        )
        return list(result.scalars().unique().all())
