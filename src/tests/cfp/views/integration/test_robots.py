import pytest

pytestmark = pytest.mark.integration


@pytest.mark.django_db
@pytest.mark.usefixtures("locmem_cache")
def test_robots_txt_content(client, django_assert_num_queries):
    """GET /robots.txt returns complete robots directives with zero DB queries."""
    with django_assert_num_queries(0):
        response = client.get("/robots.txt")

    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain"
    content = response.content.decode()
    assert content == (
        "User-agent: *\n"
        "Disallow: /me/\n"
        "Disallow: /locale/set*\n"
        "Disallow: /orga/\n"
        "Disallow: /download/\n"
        "Disallow: /redirect/\n"
        "Disallow: /api/\n"
        "Disallow: /media/\n"
    )
