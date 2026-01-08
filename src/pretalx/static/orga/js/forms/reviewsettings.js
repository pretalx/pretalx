// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const updateTotal = () => {
    let summands = []
    document
        .querySelectorAll("#score-formset .score-group")
        .forEach((element) => {
            const factor = element.querySelector("input[type=number]")
            const name = element.querySelector("input")
            if (factor && name) {
                if (factor.value === "1") {
                    summands.push(name.value)
                } else {
                    summands.push(`(${factor.value} × ${name.value})`)
                }
            }
        })
    document.querySelector("#total-score").textContent = summands.join(" + ")
}

const hideScoreWeight = (input) => {
    const scoreWeight = input.closest(".score-group").querySelector('input[name$="-weight"]')
    scoreWeight.closest(".form-group").classList.toggle("d-none", input.checked)
}
const updateIndependentScoreWeight = () => {
    document.querySelectorAll('input[name$="is_independent"]').forEach((input) => {
        input.addEventListener("change", () => hideScoreWeight(input))
        hideScoreWeight(input)
    })
}

const addNewScores = (ev) => {
    const parentElement = event.target.closest(".score-group")
    const scoresList = parentElement.querySelector(
        'input[name$="-new_scores"]',
    )
    const formID = parentElement
        .querySelector("input[type=number]")
        .id.split("-")[1]
    const newID = `new` + Math.floor(Math.random() * 1000)
    const newRow = `
    <div class="row form-group">
        <div class="col-md-9 flip ml-auto d-flex hide-label mb-1">
            <div class="mr-2 score-score">
                <input type="number" name="scores-${formID}-value_${newID}" step="0.1" class="form-control" id="id_scores-${formID}-value_${newID}" placeholder="2">
            </div>
            <div class="score-label">
                <input type="text" name="scores-${formID}-label_${newID}" maxlength="200" class="form-control" id="id_scores-${formID}-label_${newID}" placeholder="👍">
            </div>
        </div>
    </div>`
    const newElement = document.createElement("div")
    newElement.innerHTML = newRow
    parentElement.querySelector(".score-input").appendChild(newElement)
    scoresList.value += `,${newID}`
}

document
    .querySelectorAll("#score-formset input[type=number]")
    .forEach((element) => {
        if (element.value.endsWith(".0")) {
            element.value = element.value.slice(0, element.value.length - 2)
        }
    })
const addListener = () => {
    document
        .querySelectorAll(
            "#score-formset input[type=text], #score-formset input[type=number]",
        )
        .forEach((element) => {
            element.addEventListener("input", updateTotal)
        })
    document
        .querySelectorAll("#score-formset div.btn.new-score")
        .forEach((element) => {
            element.addEventListener("click", addNewScores)
        })
}

const clearOldNewScores = () => {
    document
        .querySelectorAll('input[name$="-new_scores"]')
        .forEach((input) => (input.value = ""))
}

document
    .querySelector("#score-formset #score-add")
    .addEventListener("click", () => {
        window.setTimeout(addListener, 100)
    })
document.querySelector("#phase-add").addEventListener("click", () => {
    window.setTimeout(() => {
        // get last phase and activate datetime picker for start and end field
        const lastPhase = document.querySelector(
            "#review-phases-formset .list-group-item.review-phase:last-child",
        )
        lastPhase
            .querySelectorAll('input[type="datetime-local"]')
            .forEach((input) => activateDatePicker(input))
    }, 100)
})

const initScrollPosition = () => {
    document.querySelectorAll(".keep-scroll-position").forEach((el) => {
        el.addEventListener("click", () => {
            sessionStorage.setItem("scroll-position", window.scrollY)
        })
    })
    const oldScrollY = sessionStorage.getItem("scroll-position")
    if (oldScrollY) {
        window.scroll(window.scrollX, Math.max(oldScrollY, window.innerHeight))
        sessionStorage.removeItem("scroll-position")
    }
}

onReady(addListener)
onReady(updateTotal)
onReady(clearOldNewScores)
onReady(updateIndependentScoreWeight)
onReady(initScrollPosition)
