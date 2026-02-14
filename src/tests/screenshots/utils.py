# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import time
from pathlib import Path

from django.utils import translation
from selenium.webdriver.common.by import By


def screenshot(client, name, scroll=True):
    time.sleep(1)
    if translation.get_language() != "en":
        p = name.rsplit(".", 1)
        p.insert(1, translation.get_language())
        name = ".".join(p)
    (Path("screens") / Path(name).parent).mkdir(parents=True, exist_ok=True)
    if not scroll:
        client.save_screenshot(str(Path("screens") / name))
        return
    original_size = client.get_window_size()
    required_width = client.execute_script(
        "return document.body.parentNode.scrollWidth"
    )
    required_height = client.execute_script(
        "return document.body.parentNode.scrollHeight"
    )
    client.set_window_size(required_width, required_height)
    path = str(Path("screens") / name)
    client.find_element(By.TAG_NAME, "body").screenshot(path)
    client.set_window_size(original_size["width"], original_size["height"])
