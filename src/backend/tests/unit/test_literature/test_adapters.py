"""Unit tests for literature source adapter response parsing.

Tests cover:
- PubMed XML response parsing (valid, malformed, empty)
- Crossref JSON response parsing (valid, malformed, empty)
- arXiv Atom XML response parsing (valid, malformed, empty)
- Error handling paths: 401, 403, 5xx, timeout, parse failure

Uses respx to mock HTTP responses from external APIs.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.8, 2.9
"""

from __future__ import annotations

import pytest
import respx
import httpx

from alcoabase.literature.adapters.pubmed_adapter import (
    PubMedAdapter,
    ESEARCH_URL,
    EFETCH_URL,
)
from alcoabase.literature.adapters.crossref_adapter import (
    CrossrefAdapter,
    CROSSREF_BASE_URL,
)
from alcoabase.literature.adapters.arxiv_adapter import (
    ArXivAdapter,
    ARXIV_API_URL,
)
from alcoabase.literature.exceptions import (
    AdapterAuthError,
    AdapterConnectionError,
    AdapterParseError,
    AdapterTimeoutError,
)
from alcoabase.literature.schemas.search import (
    DatePrecision,
    LiteratureSearchResult,
    PublicationType,
    SearchQuery,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def search_query() -> SearchQuery:
    """Minimal search query for testing adapters."""
    return SearchQuery(terms="cancer treatment", page_size=10, page=1)


@pytest.fixture
def pubmed_adapter() -> PubMedAdapter:
    """PubMed adapter instance for testing."""
    return PubMedAdapter()


@pytest.fixture
def crossref_adapter() -> CrossrefAdapter:
    """Crossref adapter instance for testing."""
    return CrossrefAdapter(contact_email="test@alcoabase.local")


@pytest.fixture
def arxiv_adapter() -> ArXivAdapter:
    """arXiv adapter instance (uses internal httpx client)."""
    return ArXivAdapter()


# ─── Mock Response Data ───────────────────────────────────────────────────────

VALID_ESEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
    <Count>1</Count>
    <RetMax>1</RetMax>
    <RetStart>0</RetStart>
    <IdList>
        <Id>12345678</Id>
    </IdList>
</eSearchResult>
"""

VALID_EFETCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
    <PubmedArticle>
        <MedlineCitation>
            <PMID>12345678</PMID>
            <Article>
                <ArticleTitle>Effects of Drug X on Cancer Cells</ArticleTitle>
                <Abstract>
                    <AbstractText>This study examines the effects of Drug X.</AbstractText>
                </Abstract>
                <AuthorList>
                    <Author>
                        <LastName>Smith</LastName>
                        <ForeName>John</ForeName>
                    </Author>
                    <Author>
                        <LastName>Doe</LastName>
                        <ForeName>Jane</ForeName>
                    </Author>
                </AuthorList>
                <Journal>
                    <Title>Journal of Oncology</Title>
                </Journal>
                <PublicationTypeList>
                    <PublicationType>Journal Article</PublicationType>
                </PublicationTypeList>
                <ArticleDate>
                    <Year>2023</Year>
                    <Month>06</Month>
                    <Day>15</Day>
                </ArticleDate>
            </Article>
        </MedlineCitation>
        <PubmedData>
            <ArticleIdList>
                <ArticleId IdType="doi">10.1234/test.2023.001</ArticleId>
            </ArticleIdList>
        </PubmedData>
    </PubmedArticle>
</PubmedArticleSet>
"""

EMPTY_ESEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
    <Count>0</Count>
    <RetMax>0</RetMax>
    <RetStart>0</RetStart>
    <IdList/>
</eSearchResult>
"""

VALID_CROSSREF_JSON = {
    "status": "ok",
    "message-type": "work-list",
    "message": {
        "total-results": 1,
        "items": [
            {
                "DOI": "10.1234/crossref.2023.001",
                "title": ["Advances in Cancer Immunotherapy"],
                "author": [
                    {"given": "Alice", "family": "Johnson"},
                    {"given": "Bob", "family": "Williams"},
                ],
                "abstract": "<jats:p>A comprehensive review of immunotherapy.</jats:p>",
                "container-title": ["Nature Reviews Cancer"],
                "type": "journal-article",
                "published": {"date-parts": [[2023, 5, 20]]},
                "URL": "https://doi.org/10.1234/crossref.2023.001",
            }
        ],
    },
}

EMPTY_CROSSREF_JSON = {
    "status": "ok",
    "message-type": "work-list",
    "message": {
        "total-results": 0,
        "items": [],
    },
}

VALID_ARXIV_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
    <opensearch:totalResults>1</opensearch:totalResults>
    <entry>
        <id>http://arxiv.org/abs/2301.12345v1</id>
        <title>Deep Learning for Drug Discovery</title>
        <summary>We propose a novel deep learning approach for drug discovery.</summary>
        <published>2023-01-15T12:00:00Z</published>
        <author>
            <name>Chen Wei</name>
        </author>
        <author>
            <name>Li Zhang</name>
        </author>
        <link rel="alternate" href="http://arxiv.org/abs/2301.12345v1"/>
    </entry>
</feed>
"""

EMPTY_ARXIV_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
    <opensearch:totalResults>0</opensearch:totalResults>
</feed>
"""


# ═══════════════════════════════════════════════════════════════════════════════
# PubMed Adapter Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPubMedAdapterValidResponse:
    """Test PubMed adapter with valid XML responses."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_valid_response_returns_results(
        self, pubmed_adapter: PubMedAdapter, search_query: SearchQuery
    ) -> None:
        """Valid PubMed eSearch + eFetch returns normalized results."""
        respx.get(ESEARCH_URL).mock(
            return_value=httpx.Response(200, text=VALID_ESEARCH_XML)
        )
        respx.get(EFETCH_URL).mock(
            return_value=httpx.Response(200, text=VALID_EFETCH_XML)
        )

        results = await pubmed_adapter.search(search_query)

        assert len(results) == 1
        result = results[0]
        assert isinstance(result, LiteratureSearchResult)
        assert result.title == "Effects of Drug X on Cancer Cells"
        assert result.external_id == "12345678"
        assert result.source_id == "pubmed"
        assert result.doi == "10.1234/test.2023.001"
        assert result.authors == ["Smith John", "Doe Jane"]
        assert result.journal_or_venue == "Journal of Oncology"
        assert result.publication_type == PublicationType.JOURNAL_ARTICLE
        assert result.publication_date.year == 2023
        assert result.publication_date.month == 6
        assert result.publication_date.day == 15
        assert result.date_precision == DatePrecision.DAY
        assert result.url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_response_returns_empty_list(
        self, pubmed_adapter: PubMedAdapter, search_query: SearchQuery
    ) -> None:
        """Empty eSearch IdList returns an empty results list."""
        respx.get(ESEARCH_URL).mock(
            return_value=httpx.Response(200, text=EMPTY_ESEARCH_XML)
        )

        results = await pubmed_adapter.search(search_query)

        assert results == []


class TestPubMedAdapterMalformedResponse:
    """Test PubMed adapter with malformed XML responses."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_malformed_esearch_xml_raises_parse_error(
        self, pubmed_adapter: PubMedAdapter, search_query: SearchQuery
    ) -> None:
        """Malformed XML from eSearch raises AdapterParseError."""
        respx.get(ESEARCH_URL).mock(
            return_value=httpx.Response(200, text="<broken xml><<<")
        )

        with pytest.raises(AdapterParseError):
            await pubmed_adapter.search(search_query)

    @pytest.mark.asyncio
    @respx.mock
    async def test_malformed_efetch_xml_raises_parse_error(
        self, pubmed_adapter: PubMedAdapter, search_query: SearchQuery
    ) -> None:
        """Malformed XML from eFetch raises AdapterParseError."""
        respx.get(ESEARCH_URL).mock(
            return_value=httpx.Response(200, text=VALID_ESEARCH_XML)
        )
        respx.get(EFETCH_URL).mock(
            return_value=httpx.Response(200, text="not valid xml at all <<<")
        )

        with pytest.raises(AdapterParseError):
            await pubmed_adapter.search(search_query)


class TestPubMedAdapterErrorHandling:
    """Test PubMed adapter HTTP error handling."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_401_raises_auth_error(
        self, pubmed_adapter: PubMedAdapter, search_query: SearchQuery
    ) -> None:
        """HTTP 401 from PubMed raises AdapterAuthError."""
        respx.get(ESEARCH_URL).mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        with pytest.raises(AdapterAuthError) as exc_info:
            await pubmed_adapter.search(search_query)
        assert exc_info.value.source_adapter_name == "pubmed"

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_403_raises_auth_error(
        self, pubmed_adapter: PubMedAdapter, search_query: SearchQuery
    ) -> None:
        """HTTP 403 from PubMed raises AdapterAuthError."""
        respx.get(ESEARCH_URL).mock(
            return_value=httpx.Response(403, text="Forbidden")
        )

        with pytest.raises(AdapterAuthError) as exc_info:
            await pubmed_adapter.search(search_query)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_500_raises_parse_error(
        self, pubmed_adapter: PubMedAdapter, search_query: SearchQuery
    ) -> None:
        """HTTP 500 from PubMed raises AdapterParseError (unexpected status)."""
        respx.get(ESEARCH_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(AdapterParseError):
            await pubmed_adapter.search(search_query)

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_raises_timeout_error(
        self, pubmed_adapter: PubMedAdapter, search_query: SearchQuery
    ) -> None:
        """Request timeout raises AdapterTimeoutError."""
        respx.get(ESEARCH_URL).mock(side_effect=httpx.ReadTimeout("timed out"))

        with pytest.raises(AdapterTimeoutError) as exc_info:
            await pubmed_adapter.search(search_query)
        assert exc_info.value.source_adapter_name == "pubmed"


# ═══════════════════════════════════════════════════════════════════════════════
# Crossref Adapter Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossrefAdapterValidResponse:
    """Test Crossref adapter with valid JSON responses."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_valid_response_returns_results(
        self, crossref_adapter: CrossrefAdapter, search_query: SearchQuery
    ) -> None:
        """Valid Crossref JSON returns normalized results."""
        respx.get(f"{CROSSREF_BASE_URL}/works").mock(
            return_value=httpx.Response(200, json=VALID_CROSSREF_JSON)
        )

        results = await crossref_adapter.search(search_query)

        assert len(results) == 1
        result = results[0]
        assert isinstance(result, LiteratureSearchResult)
        assert result.title == "Advances in Cancer Immunotherapy"
        assert result.external_id == "10.1234/crossref.2023.001"
        assert result.doi == "10.1234/crossref.2023.001"
        assert result.source_id == "crossref"
        assert result.authors == ["Alice Johnson", "Bob Williams"]
        assert result.journal_or_venue == "Nature Reviews Cancer"
        assert result.publication_type == PublicationType.JOURNAL_ARTICLE
        assert result.publication_date.year == 2023
        assert result.publication_date.month == 5
        assert result.publication_date.day == 20
        assert result.date_precision == DatePrecision.DAY
        # Abstract has JATS tags stripped
        assert "comprehensive review" in result.abstract
        assert "<jats:p>" not in result.abstract

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_response_returns_empty_list(
        self, crossref_adapter: CrossrefAdapter, search_query: SearchQuery
    ) -> None:
        """Empty Crossref items list returns an empty results list."""
        respx.get(f"{CROSSREF_BASE_URL}/works").mock(
            return_value=httpx.Response(200, json=EMPTY_CROSSREF_JSON)
        )

        results = await crossref_adapter.search(search_query)

        assert results == []


class TestCrossrefAdapterMalformedResponse:
    """Test Crossref adapter with malformed JSON responses."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_malformed_json_raises_parse_error(
        self, crossref_adapter: CrossrefAdapter, search_query: SearchQuery
    ) -> None:
        """Malformed JSON response raises AdapterParseError."""
        respx.get(f"{CROSSREF_BASE_URL}/works").mock(
            return_value=httpx.Response(
                200,
                text="not json {{{",
                headers={"content-type": "text/html"},
            )
        )

        with pytest.raises(AdapterParseError) as exc_info:
            await crossref_adapter.search(search_query)
        assert exc_info.value.source_adapter_name == "crossref"


class TestCrossrefAdapterErrorHandling:
    """Test Crossref adapter HTTP error handling."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_401_raises_auth_error(
        self, crossref_adapter: CrossrefAdapter, search_query: SearchQuery
    ) -> None:
        """HTTP 401 from Crossref raises AdapterAuthError."""
        respx.get(f"{CROSSREF_BASE_URL}/works").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        with pytest.raises(AdapterAuthError) as exc_info:
            await crossref_adapter.search(search_query)
        assert exc_info.value.source_adapter_name == "crossref"
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_403_raises_auth_error(
        self, crossref_adapter: CrossrefAdapter, search_query: SearchQuery
    ) -> None:
        """HTTP 403 from Crossref raises AdapterAuthError."""
        respx.get(f"{CROSSREF_BASE_URL}/works").mock(
            return_value=httpx.Response(403, text="Forbidden")
        )

        with pytest.raises(AdapterAuthError) as exc_info:
            await crossref_adapter.search(search_query)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_500_raises_connection_error(
        self, crossref_adapter: CrossrefAdapter, search_query: SearchQuery
    ) -> None:
        """HTTP 500 from Crossref raises AdapterConnectionError."""
        respx.get(f"{CROSSREF_BASE_URL}/works").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(AdapterConnectionError):
            await crossref_adapter.search(search_query)

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_raises_timeout_error(
        self, crossref_adapter: CrossrefAdapter, search_query: SearchQuery
    ) -> None:
        """Request timeout raises AdapterTimeoutError."""
        respx.get(f"{CROSSREF_BASE_URL}/works").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        with pytest.raises(AdapterTimeoutError) as exc_info:
            await crossref_adapter.search(search_query)
        assert exc_info.value.source_adapter_name == "crossref"


# ═══════════════════════════════════════════════════════════════════════════════
# arXiv Adapter Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestArXivAdapterValidResponse:
    """Test arXiv adapter with valid Atom XML responses."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_valid_response_returns_results(
        self, arxiv_adapter: ArXivAdapter, search_query: SearchQuery
    ) -> None:
        """Valid arXiv Atom XML returns normalized results."""
        respx.get(ARXIV_API_URL).mock(
            return_value=httpx.Response(200, text=VALID_ARXIV_ATOM_XML)
        )

        results = await arxiv_adapter.search(search_query)

        assert len(results) == 1
        result = results[0]
        assert isinstance(result, LiteratureSearchResult)
        assert result.title == "Deep Learning for Drug Discovery"
        assert result.external_id == "2301.12345v1"
        assert result.source_id == "arxiv"
        assert result.authors == ["Chen Wei", "Li Zhang"]
        assert result.publication_type == PublicationType.PREPRINT
        assert result.publication_date.year == 2023
        assert result.publication_date.month == 1
        assert result.publication_date.day == 15
        assert result.date_precision == DatePrecision.DAY
        assert "drug discovery" in result.abstract.lower()
        assert result.url == "http://arxiv.org/abs/2301.12345v1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_response_returns_empty_list(
        self, arxiv_adapter: ArXivAdapter, search_query: SearchQuery
    ) -> None:
        """Empty arXiv feed returns an empty results list."""
        respx.get(ARXIV_API_URL).mock(
            return_value=httpx.Response(200, text=EMPTY_ARXIV_ATOM_XML)
        )

        results = await arxiv_adapter.search(search_query)

        assert results == []


class TestArXivAdapterMalformedResponse:
    """Test arXiv adapter with malformed XML responses."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_malformed_xml_raises_parse_error(
        self, arxiv_adapter: ArXivAdapter, search_query: SearchQuery
    ) -> None:
        """Malformed Atom XML raises AdapterParseError."""
        respx.get(ARXIV_API_URL).mock(
            return_value=httpx.Response(200, text="<<<not xml at all")
        )

        with pytest.raises(AdapterParseError) as exc_info:
            await arxiv_adapter.search(search_query)
        assert exc_info.value.source_adapter_name == "arxiv"


class TestArXivAdapterErrorHandling:
    """Test arXiv adapter HTTP error handling."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_500_raises_connection_error(
        self, arxiv_adapter: ArXivAdapter, search_query: SearchQuery
    ) -> None:
        """HTTP 500 from arXiv raises AdapterConnectionError."""
        respx.get(ARXIV_API_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(AdapterConnectionError):
            await arxiv_adapter.search(search_query)

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_raises_timeout_error(
        self, arxiv_adapter: ArXivAdapter, search_query: SearchQuery
    ) -> None:
        """Request timeout raises AdapterTimeoutError."""
        respx.get(ARXIV_API_URL).mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        with pytest.raises(AdapterTimeoutError) as exc_info:
            await arxiv_adapter.search(search_query)
        assert exc_info.value.source_adapter_name == "arxiv"

    @pytest.mark.asyncio
    @respx.mock
    async def test_connection_error_raises_adapter_connection_error(
        self, arxiv_adapter: ArXivAdapter, search_query: SearchQuery
    ) -> None:
        """Network connection failure raises AdapterConnectionError."""
        respx.get(ARXIV_API_URL).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(AdapterConnectionError) as exc_info:
            await arxiv_adapter.search(search_query)
        assert exc_info.value.source_adapter_name == "arxiv"
