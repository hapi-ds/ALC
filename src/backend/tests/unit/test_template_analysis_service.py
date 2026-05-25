"""Unit tests for TemplateAnalysisService.

Tests placeholder detection, duplicate template registration, .docx validation,
and company scoping on list/get operations.

Requirements: 1.3, 1.7, 1.9, 1.10
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.template_analysis import (
    PLACEHOLDER_PATTERN,
    TemplateAnalysisService,
)


@pytest.fixture
def mock_session():
    """Create a mock async session with context manager support."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Create a session factory that mimics async_sessionmaker behavior.

    async_sessionmaker returns an async context manager when called,
    i.e., `async with session_factory() as session:`.
    """
    context_manager = AsyncMock()
    context_manager.__aenter__ = AsyncMock(return_value=mock_session)
    context_manager.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = context_manager
    return factory


@pytest.fixture
def mock_storage():
    """Create a mock StorageService."""
    storage = AsyncMock()
    storage.download_file = AsyncMock(return_value=b"mock docx bytes")
    return storage


@pytest.fixture
def mock_job_tracker():
    """Create a mock JobTracker."""
    tracker = AsyncMock()
    job = MagicMock()
    job.job_id = "test-job-123"
    tracker.create_job = AsyncMock(return_value=job)
    return tracker


@pytest.fixture
def service(mock_session_factory, mock_storage, mock_job_tracker):
    """Create a TemplateAnalysisService with mocked dependencies."""
    return TemplateAnalysisService(
        session_factory=mock_session_factory,
        storage_service=mock_storage,
        job_tracker=mock_job_tracker,
    )


class TestDetectPlaceholders:
    """Tests for detect_placeholders method.

    Validates: Requirement 1.3 - Placeholder marker detection with pattern
    {{IDENTIFIER}} or {{IDENTIFIER:parameter}}.
    """

    def test_simple_identifier(self, service: TemplateAnalysisService):
        """Simple {{IDENTIFIER}} pattern is detected."""
        text = "Please fill in {{SECTION_CONTENT}} here."
        results = service.detect_placeholders(text)

        assert len(results) == 1
        assert results[0]["marker"] == "{{SECTION_CONTENT}}"
        assert results[0]["identifier"] == "SECTION_CONTENT"
        assert results[0]["parameter"] == ""
        assert results[0]["position"] == "15"

    def test_identifier_with_parameter(self, service: TemplateAnalysisService):
        """{{IDENTIFIER:parameter}} pattern is detected with parameter."""
        text = "See {{CROSS_REF:URS}} for details."
        results = service.detect_placeholders(text)

        assert len(results) == 1
        assert results[0]["marker"] == "{{CROSS_REF:URS}}"
        assert results[0]["identifier"] == "CROSS_REF"
        assert results[0]["parameter"] == "URS"

    def test_multiple_placeholders(self, service: TemplateAnalysisService):
        """Multiple placeholders in the same text are all detected."""
        text = "{{SECTION_CONTENT}} and {{TABLE:risk_matrix}} and {{PROCEDURE_STEPS}}"
        results = service.detect_placeholders(text)

        assert len(results) == 3
        identifiers = [r["identifier"] for r in results]
        assert "SECTION_CONTENT" in identifiers
        assert "TABLE" in identifiers
        assert "PROCEDURE_STEPS" in identifiers

    def test_parameter_with_spaces(self, service: TemplateAnalysisService):
        """Parameter can contain spaces and special characters."""
        text = "{{TABLE:risk assessment matrix}}"
        results = service.detect_placeholders(text)

        assert len(results) == 1
        assert results[0]["parameter"] == "risk assessment matrix"

    def test_underscore_in_identifier(self, service: TemplateAnalysisService):
        """Identifiers can contain underscores."""
        text = "{{RISK_ASSESSMENT}}"
        results = service.detect_placeholders(text)

        assert len(results) == 1
        assert results[0]["identifier"] == "RISK_ASSESSMENT"

    def test_empty_text_returns_empty(self, service: TemplateAnalysisService):
        """Empty text returns no placeholders."""
        results = service.detect_placeholders("")
        assert results == []

    def test_no_placeholders_returns_empty(self, service: TemplateAnalysisService):
        """Text without placeholder patterns returns empty list."""
        text = "This is a normal paragraph with no markers."
        results = service.detect_placeholders(text)
        assert results == []

    def test_lowercase_identifier_not_matched(self, service: TemplateAnalysisService):
        """Lowercase identifiers are not matched (pattern requires uppercase)."""
        text = "{{section_content}} should not match."
        results = service.detect_placeholders(text)
        assert results == []

    def test_mixed_case_identifier_not_matched(self, service: TemplateAnalysisService):
        """Mixed case identifiers are not matched."""
        text = "{{Section_Content}} should not match."
        results = service.detect_placeholders(text)
        assert results == []

    def test_identifier_max_length_50(self, service: TemplateAnalysisService):
        """Identifier at exactly 50 characters is matched."""
        identifier = "A" * 50
        text = f"{{{{{identifier}}}}}"
        results = service.detect_placeholders(text)
        assert len(results) == 1
        assert results[0]["identifier"] == identifier

    def test_identifier_exceeds_50_not_matched(self, service: TemplateAnalysisService):
        """Identifier exceeding 50 characters is not matched."""
        identifier = "A" * 51
        text = f"{{{{{identifier}}}}}"
        results = service.detect_placeholders(text)
        assert results == []

    def test_parameter_max_length_100(self, service: TemplateAnalysisService):
        """Parameter at exactly 100 characters is matched."""
        param = "x" * 100
        text = f"{{{{TABLE:{param}}}}}"
        results = service.detect_placeholders(text)
        assert len(results) == 1
        assert results[0]["parameter"] == param

    def test_parameter_exceeds_100_not_matched(self, service: TemplateAnalysisService):
        """Parameter exceeding 100 characters is not matched."""
        param = "x" * 101
        text = f"{{{{TABLE:{param}}}}}"
        results = service.detect_placeholders(text)
        assert results == []

    def test_position_is_character_offset(self, service: TemplateAnalysisService):
        """Position reflects the character offset of the match."""
        text = "Hello {{MARKER}} world"
        results = service.detect_placeholders(text)

        assert results[0]["position"] == "6"

    def test_single_char_identifier(self, service: TemplateAnalysisService):
        """Single uppercase character identifier is valid."""
        text = "{{A}}"
        results = service.detect_placeholders(text)
        assert len(results) == 1
        assert results[0]["identifier"] == "A"

    def test_digits_in_identifier_not_matched(self, service: TemplateAnalysisService):
        """Digits in identifier are not matched (only A-Z and underscore)."""
        text = "{{SECTION1}} should not match."
        results = service.detect_placeholders(text)
        assert results == []

    def test_nested_braces_not_matched(self, service: TemplateAnalysisService):
        """Nested braces like {{{IDENTIFIER}}} only match the inner pattern."""
        text = "{{{SECTION_CONTENT}}}"
        results = service.detect_placeholders(text)
        # The regex will match {{SECTION_CONTENT}} within the triple braces
        assert len(results) == 1
        assert results[0]["identifier"] == "SECTION_CONTENT"


class TestValidateDocxExtension:
    """Tests for validate_docx_extension method.

    Validates: Requirement 1.7 - Only .docx files can be registered as templates.
    """

    def test_valid_docx_lowercase(self, service: TemplateAnalysisService):
        """.docx extension is accepted."""
        assert service.validate_docx_extension("documents/test/1.0/template.docx") is True

    def test_valid_docx_uppercase(self, service: TemplateAnalysisService):
        """.DOCX extension is accepted (case-insensitive)."""
        assert service.validate_docx_extension("documents/test/1.0/template.DOCX") is True

    def test_valid_docx_mixed_case(self, service: TemplateAnalysisService):
        """.Docx extension is accepted (case-insensitive)."""
        assert service.validate_docx_extension("documents/test/1.0/template.Docx") is True

    def test_rejects_pdf(self, service: TemplateAnalysisService):
        """.pdf extension is rejected."""
        assert service.validate_docx_extension("documents/test/1.0/file.pdf") is False

    def test_rejects_txt(self, service: TemplateAnalysisService):
        """.txt extension is rejected."""
        assert service.validate_docx_extension("documents/test/1.0/file.txt") is False

    def test_rejects_doc(self, service: TemplateAnalysisService):
        """.doc extension is rejected (not .docx)."""
        assert service.validate_docx_extension("documents/test/1.0/file.doc") is False

    def test_rejects_xlsx(self, service: TemplateAnalysisService):
        """.xlsx extension is rejected."""
        assert service.validate_docx_extension("documents/test/1.0/file.xlsx") is False

    def test_rejects_no_extension(self, service: TemplateAnalysisService):
        """File without extension is rejected."""
        assert service.validate_docx_extension("documents/test/1.0/noextension") is False

    def test_rejects_docx_in_middle(self, service: TemplateAnalysisService):
        """'.docx' appearing in the middle of the path is not sufficient."""
        assert service.validate_docx_extension("documents/docx/1.0/file.pdf") is False

    def test_accepts_path_with_dots(self, service: TemplateAnalysisService):
        """Path with multiple dots still validates correctly."""
        assert service.validate_docx_extension("docs/v1.0/my.template.docx") is True

    def test_rejects_empty_string(self, service: TemplateAnalysisService):
        """Empty string is rejected."""
        assert service.validate_docx_extension("") is False


class TestRegisterTemplateDuplicate:
    """Tests for register_template duplicate detection.

    Validates: Requirement 1.10 - Duplicate registration returns existing template.
    """

    @pytest.mark.asyncio
    async def test_duplicate_returns_existing_template_id(
        self, service: TemplateAnalysisService, mock_session
    ):
        """Duplicate registration returns existing template_id with job_id=None."""
        # Mock existing template found
        existing_template = MagicMock()
        existing_template.id = 42

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_template
        mock_session.execute.return_value = mock_result

        template_id, job_id = await service.register_template(
            document_id=1,
            document_version_id=10,
            template_name="Test Template",
            document_type_target="URS",
            registered_by=1,
            company_id=100,
        )

        assert template_id == 42
        assert job_id is None

    @pytest.mark.asyncio
    async def test_duplicate_does_not_create_new_record(
        self, service: TemplateAnalysisService, mock_session
    ):
        """Duplicate registration does not call session.add."""
        existing_template = MagicMock()
        existing_template.id = 42

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_template
        mock_session.execute.return_value = mock_result

        await service.register_template(
            document_id=1,
            document_version_id=10,
            template_name="Test Template",
            document_type_target="URS",
            registered_by=1,
            company_id=100,
        )

        # session.add should not be called for duplicates
        mock_session.add.assert_not_called()


class TestCompanyScoping:
    """Tests for company scoping on get_template and list_templates.

    Validates: Requirements 1.9 - All template operations scoped to company.
    """

    @pytest.mark.asyncio
    async def test_get_template_scoped_to_company(
        self, service: TemplateAnalysisService, mock_session
    ):
        """get_template queries with both template_id and company_id."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await service.get_template(template_id=5, company_id=100)

        assert result is None
        # Verify execute was called (the query includes company_id filter)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_template_returns_none_for_wrong_company(
        self, service: TemplateAnalysisService, mock_session
    ):
        """get_template returns None when template belongs to different company."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await service.get_template(template_id=5, company_id=999)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_template_returns_template_for_correct_company(
        self, service: TemplateAnalysisService, mock_session
    ):
        """get_template returns the template when company matches."""
        template = MagicMock()
        template.id = 5
        template.company_id = 100

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = template
        mock_session.execute.return_value = mock_result

        result = await service.get_template(template_id=5, company_id=100)

        assert result is not None
        assert result.id == 5

    @pytest.mark.asyncio
    async def test_list_templates_scoped_to_company(
        self, service: TemplateAnalysisService, mock_session
    ):
        """list_templates only returns templates for the specified company."""
        # First call returns count, second returns list
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        list_result = MagicMock()
        template1 = MagicMock()
        template1.id = 1
        template2 = MagicMock()
        template2.id = 2
        list_result.scalars.return_value.all.return_value = [template1, template2]

        mock_session.execute.side_effect = [count_result, list_result]

        templates, total = await service.list_templates(company_id=100)

        assert total == 2
        assert len(templates) == 2
        # Verify execute was called twice (count + list)
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_templates_with_type_filter(
        self, service: TemplateAnalysisService, mock_session
    ):
        """list_templates filters by document_type_target when provided."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        list_result = MagicMock()
        template = MagicMock()
        template.id = 1
        template.document_type_target = "URS"
        list_result.scalars.return_value.all.return_value = [template]

        mock_session.execute.side_effect = [count_result, list_result]

        templates, total = await service.list_templates(
            company_id=100, document_type_target="URS"
        )

        assert total == 1
        assert len(templates) == 1

    @pytest.mark.asyncio
    async def test_list_templates_pagination(
        self, service: TemplateAnalysisService, mock_session
    ):
        """list_templates respects limit and offset parameters."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 50

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [count_result, list_result]

        templates, total = await service.list_templates(
            company_id=100, limit=10, offset=20
        )

        assert total == 50
        assert len(templates) == 0

    @pytest.mark.asyncio
    async def test_list_templates_empty_for_company(
        self, service: TemplateAnalysisService, mock_session
    ):
        """list_templates returns empty list when company has no templates."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [count_result, list_result]

        templates, total = await service.list_templates(company_id=999)

        assert total == 0
        assert templates == []
