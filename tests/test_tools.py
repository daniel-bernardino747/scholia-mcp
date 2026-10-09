import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from scholia_mcp.server import create_server
from scholia_mcp.store import open_store


@pytest.fixture
def store(database_url, embedder):
    with open_store(database_url, embedder, "english") as store:
        yield store


@pytest.fixture
async def client(store):
    async with Client(create_server(store)) as client:
        yield client


async def save(client, **fields):
    note = {"tags": [], "sources": [], "origin_agent": "claude-code", **fields}
    return (await client.call_tool("save_note", note)).structured_content


async def search(client, query, **options):
    result = await client.call_tool("search_notes", {"query": query, **options})
    return result.structured_content["results"]


async def test_saved_note_is_found_by_an_exact_term_in_its_body(client):
    saved = await save(
        client,
        title="Hybrid search design",
        body="We combine both rankings with RRF (reciprocal rank fusion).",
    )

    results = await search(client, "RRF")

    assert results[0]["id"] == saved["id"]
    assert results[0]["title"] == "Hybrid search design"
    assert results[0]["status"] == "active"


async def test_saved_note_is_found_by_a_synonym_that_shares_no_term(client):
    await save(client, title="Morning routine", body="Espresso before nine, never after.")
    car = await save(client, title="Buying a car", body="Electric cars cost less to run.")

    results = await search(client, "automobile")

    assert results[0]["id"] == car["id"]


async def test_term_search_ignores_accents(client):
    godel = await save(client, title="Incompleteness", body="Gödel's theorem, explained simply.")
    await save(client, title="Unrelated", body="Lorem ipsum dolor sit amet.")

    results = await search(client, "godel")

    assert results[0]["id"] == godel["id"]


async def test_superseding_note_hides_the_old_one_from_default_search(client):
    old = await save(client, title="Coffee", body="Espresso helps my focus.")
    new = await save(
        client,
        title="Coffee, revised",
        body="Espresso after noon wrecks my sleep; switching to decaf.",
        supersedes=old["id"],
    )

    results = await search(client, "espresso")

    assert [r["id"] for r in results] == [new["id"]]
    assert new["supersedes"] == old["id"]


async def test_superseded_note_stays_searchable_on_request(client):
    old = await save(client, title="Coffee", body="Espresso helps my focus.")
    new = await save(client, title="Coffee, revised", body="Decaf only.", supersedes=old["id"])

    results = await search(client, "espresso focus", include_superseded=True)

    assert {r["id"]: r["status"] for r in results} == {
        old["id"]: "superseded",
        new["id"]: "active",
    }


async def test_superseding_a_note_that_is_not_active_fails_and_saves_nothing(client):
    old = await save(client, title="Coffee", body="Espresso helps my focus.")
    await save(client, title="Coffee v2", body="Decaf only.", supersedes=old["id"])

    with pytest.raises(ToolError, match="No active note"):
        await save(client, title="Coffee v3", body="Tea instead.", supersedes=old["id"])

    titles = [r["title"] for r in await search(client, "coffee", include_superseded=True)]
    assert sorted(titles) == ["Coffee", "Coffee v2"]


async def test_tags_are_normalized_to_lowercase_without_accents(client):
    saved = await save(client, title="Pricing", body="x", tags=["Preço", " SaaS ", "saas", "日本"])

    assert saved["tags"] == ["preco", "saas", "日本"]


async def test_tag_filter_keeps_only_notes_with_any_given_tag(client):
    tagged = await save(client, title="Espresso", body="Espresso notes.", tags=["coffee"])
    await save(client, title="Espresso machine", body="Espresso machines.", tags=["gear"])

    results = await search(client, "espresso", tags=["Coffee"])

    assert [r["id"] for r in results] == [tagged["id"]]


async def test_search_returns_at_most_limit_results(client):
    for n in range(3):
        await save(client, title=f"Espresso {n}", body="Espresso.")

    assert len(await search(client, "espresso", limit=2)) == 2


async def test_tag_filter_finds_matches_beyond_the_nearest_neighbours(client):
    # A tag on half the notes looks unselective, so the planner walks the HNSW
    # index, whose default search stops after ~40 candidates: here all of them
    # closer to the query than any tagged note, and none carrying the tag.
    for n in range(300):
        await save(client, title=f"Car {n}", body="Cars and automobiles.", tags=["gear"])
        await save(client, title=f"Night {n}", body="Insomnia and sleep.", tags=["health"])

    results = await search(client, "car", tags=["health"], limit=5)

    assert [r["title"].split()[0] for r in results] == ["Night"] * 5


@pytest.fixture
async def strict_client(database_url, embedder):
    with open_store(database_url, embedder, "english", min_similarity=0.5) as store:
        async with Client(create_server(store)) as client:
            yield client


async def test_with_a_similarity_floor_an_unrelated_query_finds_nothing(strict_client):
    await save(strict_client, title="Buying a car", body="Electric cars cost less to run.")

    assert await search(strict_client, "insomnia") == []


async def test_with_a_similarity_floor_a_term_match_is_still_found(strict_client):
    saved = await save(strict_client, title="Gödel", body="Cars, automobiles, vehicles.")

    results = await search(strict_client, "godel")

    assert [r["id"] for r in results] == [saved["id"]]
