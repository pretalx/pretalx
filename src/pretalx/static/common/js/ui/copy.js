// SPDX-FileCopyrightText: 2018-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const copyFlashState = new WeakMap()

const restoreCopyAttribute = (element, name, value) => {
    if (value === null) {
        element.removeAttribute(name)
    } else {
        element.setAttribute(name, value)
    }
}

const flashTooltip = (element, message, duration) => {
    let state = copyFlashState.get(element)
    if (state) {
        clearTimeout(state.timer)
    } else {
        state = {
            toggle: element.getAttribute("data-toggle"),
            tooltip: element.getAttribute("data-tooltip"),
            title: element.getAttribute("title"),
        }
        copyFlashState.set(element, state)
    }
    element.dataset.tooltip = message
    element.removeAttribute("title")
    element.setAttribute("data-toggle", "tooltip")
    state.timer = setTimeout(() => {
        restoreCopyAttribute(element, "data-toggle", state.toggle)
        restoreCopyAttribute(element, "data-tooltip", state.tooltip)
        restoreCopyAttribute(element, "title", state.title)
        copyFlashState.delete(element)
    }, duration)
}

let copyStatusRegion = null

const announceCopy = (message) => {
    copyStatusRegion.textContent = ""
    setTimeout(() => {
        copyStatusRegion.textContent = message
    }, 100)
}

const copyText = (element) => {
    if (!element.dataset.copyFrom) return element.dataset.destination
    const input = document.getElementById(element.dataset.copyFrom)
    return input.value || input.placeholder
}

const performCopy = (element) => {
    const text = copyText(element)
    if (element.dataset.copyFrom && !text) return
    navigator.clipboard.writeText(text).then(
        () => {
            const message = element.dataset.successMessage || "Copied!"
            flashTooltip(element, message, 1000)
            announceCopy(message)
        },
        () => {
            const message = element.dataset.errorMessage || "Failed to copy"
            flashTooltip(element, message, 2000)
            announceCopy(message)
        },
    )
}

onReady(() => {
    copyStatusRegion = document.createElement("div")
    copyStatusRegion.className = "sr-only"
    copyStatusRegion.setAttribute("role", "status")
    document.body.appendChild(copyStatusRegion)

    document.addEventListener("click", (event) => {
        const element = event.target.closest(".copyable-text")
        if (element) performCopy(element)
    })

    document.addEventListener("keydown", (event) => {
        if (event.key !== " " && event.key !== "Enter") return
        const element = event.target.closest(".copyable-text")
        if (!element) return
        event.preventDefault()
        performCopy(element)
    })
})
