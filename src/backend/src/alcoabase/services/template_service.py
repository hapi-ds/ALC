"""Template service for creating and managing report templates.

Provides template lifecycle management including creation with UUID
generation, Field-UUID assignment, immutability enforcement after
ReadOnly status, and retrieval operations.

References:
    - Design doc Section 4: Template Service
    - Requirements 3: Template creation, Field-UUID assignment, immutability
    - Requirements 18.6, 18.7: Enhanced template creation with elements format
"""

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alcoabase.models.template import Template, TemplateField
from alcoabase.models.template_version import TemplateVersion, TemplateVersionField
from alcoabase.schemas.template import (
    BooleanFieldConfig,
    DateFieldConfig,
    FloatFieldConfig,
    IntegerFieldConfig,
    TextFieldConfig,
)
from alcoabase.services.uuid_service import UUIDService

# Mapping from field type to its config schema class
FIELD_CONFIG_SCHEMAS: dict[str, type] = {
    "Text": TextFieldConfig,
    "Float": FloatFieldConfig,
    "Integer": IntegerFieldConfig,
    "Date": DateFieldConfig,
    "Boolean": BooleanFieldConfig,
}


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
        company_id: int | None = None,
    ) -> Template:
        """Create a new template with Document-UUID and Field-UUIDs.

        Supports both the legacy format (json_schema with `fields` key) and
        the enhanced format (json_schema with `elements` key). Detects the
        format automatically and processes accordingly.

        For the enhanced format:
        - Validates at least one field element exists
        - Parses and validates type-specific field configs
        - Assigns FLD-XXXXXXXX UUIDs to field elements
        - Assigns CB-XXXXXXXX UUIDs to content block elements
        - Stores config as JSONB

        Args:
            session: Active async database session.
            name: Template name.
            json_schema: Template schema dict with either:
                Legacy: {"fields": [{"label": "...", "type": "Text|..."}]}
                Enhanced: {"elements": [{"element_type": "field"|"content_block", ...}]}
            user_id: ID of the creating user.
            company_id: ID of the company (tenant) owning the template.

        Returns:
            The created Template instance with fields loaded.

        Raises:
            ValueError: If Field-UUID uniqueness validation fails,
                json_schema format is invalid, no field elements exist,
                or field config validation fails.
        """
        if not isinstance(json_schema, dict):
            raise ValueError("json_schema must be a dict")

        # Detect format: enhanced (elements) vs legacy (fields)
        if "elements" in json_schema:
            return await self._create_template_enhanced(
                session, name, json_schema, user_id, company_id
            )
        elif "fields" in json_schema:
            return await self._create_template_legacy(
                session, name, json_schema, user_id, company_id
            )
        else:
            raise ValueError(
                "json_schema must contain either an 'elements' key "
                "(enhanced format) or a 'fields' key (legacy format)"
            )

    async def _create_template_legacy(
        self,
        session: AsyncSession,
        name: str,
        json_schema: dict,
        user_id: int,
        company_id: int | None = None,
    ) -> Template:
        """Create a template using the legacy fields format.

        Args:
            session: Active async database session.
            name: Template name.
            json_schema: Schema with {"fields": [...]}.
            user_id: ID of the creating user.
            company_id: ID of the company (tenant) owning the template.

        Returns:
            The created Template instance with fields loaded.

        Raises:
            ValueError: If schema format is invalid or UUID collision occurs.
        """
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
            company_id=company_id,
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

    async def _create_template_enhanced(
        self,
        session: AsyncSession,
        name: str,
        json_schema: dict,
        user_id: int,
        company_id: int | None = None,
    ) -> Template:
        """Create a template using the enhanced elements format.

        Handles both field elements and content block elements. Validates
        type-specific configs, assigns appropriate UUIDs (FLD- for fields,
        CB- for content blocks), and stores config as JSONB.

        Args:
            session: Active async database session.
            name: Template name.
            json_schema: Schema with {"elements": [...]}.
            user_id: ID of the creating user.
            company_id: ID of the company (tenant) owning the template.

        Returns:
            The created Template instance with fields loaded.

        Raises:
            ValueError: If no field elements exist, config validation fails,
                or UUID collision occurs.
        """
        elements = json_schema.get("elements", [])
        if not isinstance(elements, list) or len(elements) == 0:
            raise ValueError("json_schema 'elements' must be a non-empty list")

        # Validate at least one field element exists (Requirement 18.7)
        has_field = any(
            isinstance(elem, dict) and elem.get("element_type") == "field"
            for elem in elements
        )
        if not has_field:
            raise ValueError(
                "Template must contain at least one field element"
            )

        # Validate and parse field configs for each element
        parsed_elements = self._parse_and_validate_elements(elements)

        # Generate Document-UUID for the template
        document_uuid = await self._uuid_service.generate_document_uuid(session)

        # Generate UUIDs for all elements (FLD- for fields, CB- for content blocks)
        element_uuids: list[str] = []
        for elem in parsed_elements:
            if elem["element_type"] == "field":
                element_uuids.append(self._uuid_service.generate_field_uuid())
            else:
                element_uuids.append(
                    self._uuid_service.generate_content_block_uuid()
                )

        # Validate UUID uniqueness within the template
        if len(set(element_uuids)) != len(element_uuids):
            raise ValueError(
                "UUID uniqueness violation: duplicate UUIDs generated"
            )

        # Create template record with ReadOnly status
        template = Template(
            document_uuid=document_uuid,
            name=name,
            json_schema=json_schema,
            status="ReadOnly",
            created_by=user_id,
            company_id=company_id,
        )
        session.add(template)
        await session.flush()

        # Create TemplateField records for each element
        for order, (elem, elem_uuid) in enumerate(
            zip(parsed_elements, element_uuids, strict=True)
        ):
            if elem["element_type"] == "field":
                field = TemplateField(
                    template_id=template.id,
                    field_uuid=elem_uuid,
                    field_type=elem["type"],
                    field_label=elem["label"],
                    field_order=order,
                    element_type="field",
                    config=elem.get("validated_config"),
                    required=elem.get("required", False),
                    help_text=elem.get("help_text"),
                    default_value=elem.get("default_value"),
                )
            else:
                # Content block element
                field = TemplateField(
                    template_id=template.id,
                    field_uuid=elem_uuid,
                    field_type=elem.get("content_type", "divider"),
                    field_label=elem.get("text") or "",
                    field_order=order,
                    element_type="content_block",
                    content_type=elem.get("content_type"),
                    text_content=elem.get("text"),
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

    def _parse_and_validate_elements(
        self, elements: list[dict]
    ) -> list[dict]:
        """Parse and validate each element in the enhanced schema.

        For field elements, validates the type-specific config using the
        appropriate Pydantic schema. Returns enriched element dicts with
        a `validated_config` key containing the validated config dict.

        Args:
            elements: List of raw element dicts from the JSON schema.

        Returns:
            List of validated element dicts with parsed configs.

        Raises:
            ValueError: If any element has an invalid structure or config.
        """
        parsed: list[dict] = []

        for idx, elem in enumerate(elements):
            if not isinstance(elem, dict):
                raise ValueError(
                    f"Element at index {idx} must be a dict"
                )

            element_type = elem.get("element_type")
            if element_type not in ("field", "content_block"):
                raise ValueError(
                    f"Element at index {idx} has invalid element_type: "
                    f"'{element_type}'. Must be 'field' or 'content_block'."
                )

            if element_type == "field":
                parsed.append(self._validate_field_element(elem, idx))
            else:
                parsed.append(
                    self._validate_content_block_element(elem, idx)
                )

        return parsed

    def _validate_field_element(self, elem: dict, idx: int) -> dict:
        """Validate a field element and its type-specific config.

        Args:
            elem: Raw field element dict.
            idx: Element index for error messages.

        Returns:
            Enriched element dict with validated_config key.

        Raises:
            ValueError: If field type is invalid or config validation fails.
        """
        field_type = elem.get("type")
        valid_types = ("Text", "Float", "Integer", "Date", "Boolean")
        if field_type not in valid_types:
            raise ValueError(
                f"Field element at index {idx} has invalid type: "
                f"'{field_type}'. Must be one of {valid_types}."
            )

        label = elem.get("label", "")
        if not label:
            raise ValueError(
                f"Field element at index {idx} must have a non-empty label."
            )

        # Validate config if provided
        validated_config: dict | None = None
        raw_config = elem.get("config")
        if raw_config is not None and isinstance(raw_config, dict):
            config_schema = FIELD_CONFIG_SCHEMAS.get(field_type)
            if config_schema:
                try:
                    config_instance = config_schema(**raw_config)
                    validated_config = config_instance.model_dump(
                        exclude_none=True
                    )
                except (ValidationError, ValueError) as e:
                    raise ValueError(
                        f"Field element at index {idx} ('{label}') has "
                        f"invalid config for type '{field_type}': {e}"
                    )
        elif raw_config is not None and not isinstance(raw_config, dict):
            raise ValueError(
                f"Field element at index {idx} config must be a dict or null."
            )

        return {
            "element_type": "field",
            "type": field_type,
            "label": label,
            "required": elem.get("required", False),
            "help_text": elem.get("help_text"),
            "default_value": elem.get("default_value"),
            "validated_config": validated_config,
        }

    def _validate_content_block_element(
        self, elem: dict, idx: int
    ) -> dict:
        """Validate a content block element.

        Args:
            elem: Raw content block element dict.
            idx: Element index for error messages.

        Returns:
            Validated content block element dict.

        Raises:
            ValueError: If content_type is invalid.
        """
        content_type = elem.get("content_type")
        valid_content_types = (
            "heading_h1",
            "heading_h2",
            "heading_h3",
            "paragraph",
            "divider",
        )
        if content_type not in valid_content_types:
            raise ValueError(
                f"Content block at index {idx} has invalid content_type: "
                f"'{content_type}'. Must be one of {valid_content_types}."
            )

        return {
            "element_type": "content_block",
            "content_type": content_type,
            "text": elem.get("text"),
        }

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

    async def create_version(
        self,
        session: AsyncSession,
        document_uuid: str,
        json_schema: dict,
        user_id: int,
        change_reason: str,
    ) -> TemplateVersion:
        """Create a new version for an existing template.

        Uses SELECT FOR UPDATE on the template row to prevent race conditions
        when multiple concurrent version creation requests target the same
        template. Determines the next version number, deactivates the current
        active version, and creates a new immutable version snapshot.

        Args:
            session: Active async database session (must be within a transaction).
            document_uuid: The Document-UUID of the parent template.
            json_schema: Enhanced template schema dict with elements array.
            user_id: ID of the user creating the version.
            change_reason: ALCOA+ audit reason for creating this version.

        Returns:
            The created TemplateVersion instance with fields loaded.

        Raises:
            HTTPException: 404 if template not found, 400 if template is not
                ReadOnly or schema is invalid, 409 if concurrent version
                creation is detected.
        """
        try:
            # Lock the template row with SELECT FOR UPDATE to prevent
            # concurrent version creation (Requirement 10.8)
            result = await session.execute(
                select(Template)
                .where(Template.document_uuid == document_uuid)
                .with_for_update(nowait=True)
            )
            template = result.scalar_one_or_none()
        except OperationalError:
            # NOWAIT raises OperationalError if the row is already locked
            # by another transaction (concurrent version creation in progress)
            raise HTTPException(
                status_code=409,
                detail="Version creation in progress for this template",
            )

        if template is None:
            raise HTTPException(
                status_code=404,
                detail=f"Template not found: {document_uuid}",
            )

        if template.status != "ReadOnly":
            raise HTTPException(
                status_code=400,
                detail="Cannot create a version for a template that is not ReadOnly.",
            )

        # Validate the json_schema has elements format
        if not isinstance(json_schema, dict) or "elements" not in json_schema:
            raise HTTPException(
                status_code=400,
                detail="json_schema must contain an 'elements' key",
            )

        elements = json_schema.get("elements", [])
        if not isinstance(elements, list) or len(elements) == 0:
            raise HTTPException(
                status_code=400,
                detail="json_schema 'elements' must be a non-empty list",
            )

        # Validate at least one field element exists (Requirement 18.7)
        has_field = any(
            isinstance(elem, dict) and elem.get("element_type") == "field"
            for elem in elements
        )
        if not has_field:
            raise HTTPException(
                status_code=400,
                detail="Template must contain at least one field element",
            )

        # Validate and parse elements
        try:
            parsed_elements = self._parse_and_validate_elements(elements)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
            )

        # Determine next version number: max existing + 1 (Requirement 10.5)
        max_version_result = await session.execute(
            select(func.coalesce(func.max(TemplateVersion.version_number), 0))
            .where(TemplateVersion.template_id == template.id)
        )
        max_version = max_version_result.scalar_one()
        next_version_number = max_version + 1

        # Deactivate current active version (Requirement 13.3)
        await session.execute(
            update(TemplateVersion)
            .where(
                TemplateVersion.template_id == template.id,
                TemplateVersion.is_active == True,  # noqa: E712
            )
            .values(is_active=False)
        )

        # Create new TemplateVersion with is_active=True, status="ReadOnly"
        # (Requirements 10.6, 13.4)
        version = TemplateVersion(
            template_id=template.id,
            version_number=next_version_number,
            document_uuid=document_uuid,
            json_schema=json_schema,
            status="ReadOnly",
            is_active=True,
            created_by=user_id,
            change_reason=change_reason,
        )
        session.add(version)
        await session.flush()

        # Assign Field-UUIDs to version fields and create TemplateVersionField records
        for order, elem in enumerate(parsed_elements):
            if elem["element_type"] == "field":
                field_uuid = self._uuid_service.generate_field_uuid()
                version_field = TemplateVersionField(
                    version_id=version.id,
                    field_uuid=field_uuid,
                    field_type=elem["type"],
                    field_label=elem["label"],
                    field_order=order,
                    element_type="field",
                    config=elem.get("validated_config"),
                    required=elem.get("required", False),
                    help_text=elem.get("help_text"),
                    default_value=elem.get("default_value"),
                )
            else:
                # Content block element
                field_uuid = self._uuid_service.generate_content_block_uuid()
                version_field = TemplateVersionField(
                    version_id=version.id,
                    field_uuid=field_uuid,
                    field_type=elem.get("content_type", "divider"),
                    field_label=elem.get("text") or "",
                    field_order=order,
                    element_type="content_block",
                    content_type=elem.get("content_type"),
                    text_content=elem.get("text"),
                )
            session.add(version_field)

        await session.flush()

        # Reload version with fields relationship
        result = await session.execute(
            select(TemplateVersion)
            .where(TemplateVersion.id == version.id)
            .options(selectinload(TemplateVersion.fields))
        )
        return result.scalar_one()

    async def get_version_history(
        self, session: AsyncSession, document_uuid: str
    ) -> list[TemplateVersion]:
        """Return all versions for a template, ordered by version_number DESC.

        Retrieves the complete version history for audit trail purposes,
        with the newest version first.

        Args:
            session: Active async database session.
            document_uuid: The Document-UUID of the parent template.

        Returns:
            List of TemplateVersion instances with fields loaded,
            ordered by version_number descending (newest first).

        Raises:
            HTTPException: 404 if the template is not found.
        """
        # Verify template exists
        template = await self.get_template(session, document_uuid)
        if template is None:
            raise HTTPException(
                status_code=404,
                detail=f"Template not found: {document_uuid}",
            )

        result = await session.execute(
            select(TemplateVersion)
            .where(TemplateVersion.template_id == template.id)
            .options(selectinload(TemplateVersion.fields))
            .order_by(TemplateVersion.version_number.desc())
        )
        return list(result.scalars().unique().all())

    async def get_version(
        self,
        session: AsyncSession,
        document_uuid: str,
        version_number: int,
    ) -> TemplateVersion | None:
        """Return a specific version by template UUID and version number.

        Args:
            session: Active async database session.
            document_uuid: The Document-UUID of the parent template.
            version_number: The version number to retrieve.

        Returns:
            The TemplateVersion instance with fields loaded, or None if
            the template exists but the version number does not.

        Raises:
            HTTPException: 404 if the template is not found.
        """
        # Verify template exists
        template = await self.get_template(session, document_uuid)
        if template is None:
            raise HTTPException(
                status_code=404,
                detail=f"Template not found: {document_uuid}",
            )

        result = await session.execute(
            select(TemplateVersion)
            .where(
                TemplateVersion.template_id == template.id,
                TemplateVersion.version_number == version_number,
            )
            .options(selectinload(TemplateVersion.fields))
        )
        return result.scalar_one_or_none()

    async def get_active_version(
        self, session: AsyncSession, document_uuid: str
    ) -> TemplateVersion | None:
        """Return the active version for a template (used for PDF download).

        The active version is the one with is_active=True, which is the
        latest version used for new data collection and PDF generation.

        Args:
            session: Active async database session.
            document_uuid: The Document-UUID of the parent template.

        Returns:
            The active TemplateVersion instance with fields loaded, or None
            if the template has no versions or no active version.

        Raises:
            HTTPException: 404 if the template is not found.
        """
        # Verify template exists
        template = await self.get_template(session, document_uuid)
        if template is None:
            raise HTTPException(
                status_code=404,
                detail=f"Template not found: {document_uuid}",
            )

        result = await session.execute(
            select(TemplateVersion)
            .where(
                TemplateVersion.template_id == template.id,
                TemplateVersion.is_active == True,  # noqa: E712
            )
            .options(selectinload(TemplateVersion.fields))
        )
        return result.scalar_one_or_none()
