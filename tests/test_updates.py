from email_order_reader.updates import update_info_from_release_payload


def test_update_info_selects_windows_asset_for_newer_build():
    payload = {
        "tag_name": "build-15",
        "html_url": "https://github.com/1192081163/email-order-reader/releases/tag/build-15",
        "assets": [
            {
                "name": "EmailOrderReader.dmg",
                "browser_download_url": "https://example.com/EmailOrderReader.dmg",
            },
            {
                "name": "EmailOrderReader.exe",
                "browser_download_url": "https://example.com/EmailOrderReader.exe",
            },
        ],
    }

    update = update_info_from_release_payload(
        payload,
        current_release_tag="build-14",
        current_version="0.1.0",
        platform_name="win32",
    )

    assert update is not None
    assert update.tag_name == "build-15"
    assert update.asset_name == "EmailOrderReader.exe"
    assert update.asset_url == "https://example.com/EmailOrderReader.exe"


def test_update_info_selects_macos_asset_for_newer_semver_release():
    payload = {
        "tag_name": "v1.2.0",
        "html_url": "https://github.com/1192081163/email-order-reader/releases/tag/v1.2.0",
        "assets": [
            {
                "name": "EmailOrderReader.exe",
                "browser_download_url": "https://example.com/EmailOrderReader.exe",
            },
            {
                "name": "EmailOrderReader.dmg",
                "browser_download_url": "https://example.com/EmailOrderReader.dmg",
            },
        ],
    }

    update = update_info_from_release_payload(
        payload,
        current_release_tag="v1.1.0",
        current_version="1.1.0",
        platform_name="darwin",
    )

    assert update is not None
    assert update.tag_name == "v1.2.0"
    assert update.asset_name == "EmailOrderReader.dmg"


def test_update_info_ignores_same_build_release():
    payload = {
        "tag_name": "build-15",
        "html_url": "https://github.com/1192081163/email-order-reader/releases/tag/build-15",
        "assets": [
            {
                "name": "EmailOrderReader.exe",
                "browser_download_url": "https://example.com/EmailOrderReader.exe",
            },
        ],
    }

    update = update_info_from_release_payload(
        payload,
        current_release_tag="build-15",
        current_version="0.1.0",
        platform_name="win32",
    )

    assert update is None


def test_update_info_uses_release_page_when_platform_asset_is_missing():
    payload = {
        "tag_name": "build-16",
        "html_url": "https://github.com/1192081163/email-order-reader/releases/tag/build-16",
        "assets": [
            {
                "name": "EmailOrderReader.dmg",
                "browser_download_url": "https://example.com/EmailOrderReader.dmg",
            },
        ],
    }

    update = update_info_from_release_payload(
        payload,
        current_release_tag="build-15",
        current_version="0.1.0",
        platform_name="win32",
    )

    assert update is not None
    assert update.asset_name == ""
    assert update.asset_url == ""
    assert update.release_url.endswith("/build-16")
