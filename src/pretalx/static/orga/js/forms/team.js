// SPDX-FileCopyrightText: 2021-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const reviewerInput = document.querySelector("input#id_is_reviewer")
const updateVisibility = () => {
    document.querySelector("#review-settings").classList.toggle("d-none", !reviewerInput.checked)
}
reviewerInput.addEventListener("change", updateVisibility)
updateVisibility()

