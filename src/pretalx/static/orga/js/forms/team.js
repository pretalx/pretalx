// SPDX-FileCopyrightText: 2021-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const reviewerInput = document.querySelector("input#id_is_reviewer")
const reviewSettings = document.querySelector("#review-settings")
const updateReviewVisibility = () => {
    reviewSettings.classList.toggle("show", reviewerInput.checked)
}
reviewerInput.addEventListener("change", updateReviewVisibility)
updateReviewVisibility()

const allEventsInput = document.querySelector("input#id_all_events")
const limitEventsContainer = document.querySelector("#limit-events-container")
const updateEventsVisibility = () => {
    limitEventsContainer.classList.toggle("show", !allEventsInput.checked)
}
allEventsInput.addEventListener("change", updateEventsVisibility)
updateEventsVisibility()
