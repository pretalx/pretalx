// SPDX-FileCopyrightText: 2021-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

onReady(() => {
    const reviewerInput = document.querySelector("input#id_is_reviewer")
    const reviewSettings = document.querySelector("#review-settings")
    if (reviewerInput && reviewSettings) {
        const updateReviewVisibility = () => {
            setBlockVisibility(reviewSettings, reviewerInput.checked)
        }
        reviewerInput.addEventListener("change", updateReviewVisibility)
        updateReviewVisibility()
    }
})
