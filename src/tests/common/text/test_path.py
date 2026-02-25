import pytest

from pretalx.common.text.path import hashed_path, safe_filename

pytestmark = pytest.mark.unit


@pytest.fixture
def _deterministic_random(monkeypatch):
    monkeypatch.setattr(
        "pretalx.common.text.path.get_random_string", lambda x: "aaaaaaa"
    )


@pytest.mark.parametrize(
    ("original_name", "target_name", "upload_dir", "expected"),
    (
        ("photo.jpg", "avatar", None, "avatar_aaaaaaa.jpg"),
        ("photo.jpg", "logo", "event/img/", "event/img/logo_aaaaaaa.jpg"),
        (
            "user_file.png",
            "image",
            "submissions/ABC/",
            "submissions/ABC/image_aaaaaaa.png",
        ),
        ("file.tar.gz", "archive", None, "archive_aaaaaaa.gz"),
        ("noext", "noext", None, "noext_aaaaaaa"),
        ("/absolute/path/doc.pdf", "doc", "resources/", "resources/doc_aaaaaaa.pdf"),
        ("relative/path/img.png", "img", None, "img_aaaaaaa.png"),
    ),
)
@pytest.mark.usefixtures("_deterministic_random")
def test_hashed_path(original_name, target_name, upload_dir, expected):
    result = hashed_path(original_name, target_name=target_name, upload_dir=upload_dir)

    assert result == expected


@pytest.mark.usefixtures("_deterministic_random")
def test_hashed_path_truncates_long_names(settings):
    """When the full path exceeds max_length, the file_root is truncated."""
    settings.MEDIA_ROOT = "/m"

    result = hashed_path("f.png", target_name="longname", max_length=20)

    assert result == "longn_aaaaaaa.png"


@pytest.mark.usefixtures("_deterministic_random")
def test_hashed_path_no_max_length():
    """When max_length is 0 (falsy), no truncation is applied."""
    result = hashed_path("f.png", target_name="longname", max_length=0)

    assert result == "longname_aaaaaaa.png"


@pytest.mark.usefixtures("_deterministic_random")
def test_hashed_path_excess_larger_than_root(settings):
    """When the excess exceeds the file_root length, truncation is skipped
    (the root can't be shortened enough)."""
    settings.MEDIA_ROOT = "/very/long/media/root/path/that/makes/things/exceed"

    result = hashed_path("f.png", target_name="ab", max_length=10)

    assert result == "ab_aaaaaaa.png"


@pytest.mark.parametrize(
    ("filename", "expected"),
    (
        ("hello.txt", "hello.txt"),
        ("ö", "o"),
        ("å", "a"),
        ("ø", ""),
        ("α", ""),
        ("naïve.pdf", "naive.pdf"),
        ("café", "cafe"),
        ("", ""),
    ),
)
def test_safe_filename(filename, expected):
    assert safe_filename(filename) == expected
