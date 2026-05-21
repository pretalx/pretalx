// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const updateVisibility = () => {
    setBlockVisibility(
        "#show-if-state",
        ["accepted", "confirmed"].includes(
            document.querySelector("#id_state").value,
        ),
    )
}

if (document.querySelector("#id_state")) {
    document
        .querySelector("#id_state")
        .addEventListener("change", updateVisibility)
    updateVisibility()
}
