// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/*
 * RANGE SLIDER
 */
const slider = document.querySelector("#review-count")

if (slider) {
    const max = parseInt(slider.dataset.max)
    let params =
        new URLSearchParams(window.location.search).get("review-count") || ","
    params = params.split(",")

    const minInitial = params ? params[0] : 0
    const maxInitial = params ? params[1] : max

    const reviewSlider = new rSlider({
        target: "#review-count",
        values: Array(max + 1)
            .fill()
            .map((element, index) => index),
        range: true,
        tooltip: false,
        scale: true,
        labels: true,
        width: "270px",
        set: [parseInt(minInitial), parseInt(maxInitial)],
    })
}

/*
 * REVIEW SELECTION
 *
 * When a radio button is selected (or has been selected from the start):
 * add the active class to its unmark-radio element
 * Count both classes of radio buttons and update counters
 * When .unmark-radio is clicked, deactivate its neighbored labels and update count
 */
let count = { accept: 0, reject: 0 }

const updateCount = () => {
    const acceptLabel = document.querySelector("#acceptCount")
    const rejectLabel = document.querySelector("#rejectCount")
    const submitBar = document.querySelector("#submitBar")
    const submitText = document.querySelector("#submitText")

    if (!acceptLabel || !rejectLabel || !submitBar) return

    count.accept = 0
    count.reject = 0
    document
        .querySelectorAll(".review-table tbody .reject input[type=radio]")
        .forEach((element) => {
            if (element.checked) {
                count.reject += 1
                element.parentElement.parentElement
                    .querySelector(".unmark-radio")
                    ?.classList.add("active")
            }
        })
    document
        .querySelectorAll(".review-table tbody .accept input[type=radio]")
        .forEach((element) => {
            if (element.checked) {
                count.accept += 1
                element.parentElement.parentElement
                    .querySelector(".unmark-radio")
                    ?.classList.add("active")
            }
        })
    if (count.accept + count.reject == 0) {
        submitBar.classList.add("d-none")
    } else {
        submitBar.classList.remove("d-none")
    }
    if (acceptLabel.firstChild) acceptLabel.removeChild(acceptLabel.firstChild)
    acceptLabel.appendChild(document.createTextNode(count.accept))
    if (rejectLabel.firstChild) rejectLabel.removeChild(rejectLabel.firstChild)
    rejectLabel.appendChild(document.createTextNode(count.reject))

    if (submitText) submitText.classList.remove("d-none")
}

const initReviewRadios = (container = document) => {
    // When container is document, use full selector. When container is the swapped
    // table-content div, use simpler selector since .review-table is outside it.
    const radioSelector = container === document
        ? ".review-table tbody .radio input[type=radio]"
        : "tbody .radio input[type=radio]"
    const unmarkSelector = container === document
        ? ".review-table tbody .unmark-radio"
        : "tbody .unmark-radio"

    container.querySelectorAll(radioSelector).forEach((element) => {
        element.addEventListener("click", () => {
            updateCount()
        })
    })

    container.querySelectorAll(unmarkSelector).forEach((element) => {
        element.addEventListener("click", (ev) => {
            ev.target.parentElement.parentElement
                .querySelectorAll("input[type=radio]")
                .forEach((rad) => {
                    rad.checked = false
                })
            ev.target.parentElement.classList.remove("active")
            updateCount()
        })
    })
}

const initHeaderRadios = () => {
    const acceptAll = document.getElementById("a-all")
    if (acceptAll && !acceptAll.dataset.initialized) {
        acceptAll.dataset.initialized = "true"
        acceptAll.addEventListener("click", () => {
            document.querySelectorAll("tbody .action-row").forEach((td) => {
                if (
                    td.querySelector(".radio.reject input") &&
                    !td.querySelector(".radio.reject input").checked
                ) {
                    const acceptInput = td.querySelector(".radio.accept input")
                    if (acceptInput) acceptInput.checked = true
                }
            })
            updateCount()
        })
    }

    const rejectAll = document.getElementById("r-all")
    if (rejectAll && !rejectAll.dataset.initialized) {
        rejectAll.dataset.initialized = "true"
        rejectAll.addEventListener("click", () => {
            document.querySelectorAll("tbody .action-row").forEach((td) => {
                if (
                    td.querySelector(".radio.accept input") &&
                    !td.querySelector(".radio.accept input").checked
                ) {
                    const rejectInput = td.querySelector(".radio.reject input")
                    if (rejectInput) rejectInput.checked = true
                }
            })
            updateCount()
        })
    }

    const clearAll = document.getElementById("u-all")
    if (clearAll && !clearAll.dataset.initialized) {
        clearAll.dataset.initialized = "true"
        clearAll.addEventListener("click", (ev) => {
            document.querySelectorAll(".review-table tbody input[type=radio]").forEach((rad) => {
                rad.checked = false
            })
            ev.target.parentElement.classList.remove("active")
            updateCount()
        })
    }
}

onReady(() => {
    initReviewRadios()
    initHeaderRadios()
    updateCount()
})

// Re-initialize after HTMX swaps table content
document.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target
    if (target.classList.contains("table-content")) {
        initReviewRadios(target)
        initHeaderRadios()
        updateCount()
    }
})
