// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/**
 * Fix for dropdowns in scrollable containers by applying fixed positioning.
 */

class DetailsDropdownFix {
    constructor(element, scrollContainer, scrollParent) {
        this.details = element
        this.content = this.details.querySelector(".dropdown-content")
        this.scrollContainer = scrollContainer
        this.scrollParent = scrollParent
        this.init()
    }

    init() {
        this.details.addEventListener("toggle", () => {
            this.details.open ? this.open() : this.close()
        })
        this.scrollContainer.addEventListener("scroll", () => {
            if (this.details.open) this.updatePosition()
        })
        this.scrollParent.addEventListener("scroll", () => {
            if (this.details.open) this.updatePosition()
        })
        window.addEventListener("resize", () => {
            if (this.details.open) this.updatePosition()
        })
    }

    updatePosition() {
        const summary = this.details.querySelector("summary")
        if (!summary) return

        const triggerRect = summary.getBoundingClientRect()
        const contentRect = this.content.getBoundingClientRect()
        const viewportHeight = window.innerHeight

        // Determine if we should flip the dropdown upward
        const spaceBelow = viewportHeight - triggerRect.bottom
        const spaceAbove = triggerRect.top
        const shouldFlip =
            spaceBelow < contentRect.height && spaceAbove > spaceBelow

        // Position the dropdown
        if (shouldFlip) {
            this.content.style.top = "auto"
            this.content.style.bottom =
                viewportHeight - triggerRect.top + 2 + "px"
            this.content.classList.add("dropdown-flipped")
        } else {
            this.content.style.top = triggerRect.bottom + 2 + "px"
            this.content.style.bottom = "auto"
            this.content.classList.remove("dropdown-flipped")
        }

        this.content.style.left = triggerRect.left + "px"

        if (this.content.classList.contains("dropdown-content-sw")) {
            this.content.style.left = "auto"
            this.content.style.right =
                window.innerWidth - triggerRect.right + "px"
        } else if (this.content.classList.contains("dropdown-content-s")) {
            const contentWidth = contentRect.width
            this.content.style.left =
                triggerRect.left +
                triggerRect.width / 2 -
                contentWidth +
                "px"
        }
    }

    open() {
        this.content.style.position = "fixed"
        this.content.style.display = "block"
        requestAnimationFrame(() => this.updatePosition())
    }

    close() {
        this.content.classList.remove("dropdown-flipped")

        // Reset all positioning styles
        this.content.style.position = ""
        this.content.style.display = ""
        this.content.style.top = ""
        this.content.style.bottom = ""
        this.content.style.left = ""
        this.content.style.right = ""
    }
}

function fixDropdownsInScrollContainer(scrollContainer, scrollParent) {
    if (!scrollContainer) return

    scrollContainer.querySelectorAll("details.dropdown").forEach((details) => {
        new DetailsDropdownFix(details, scrollContainer, scrollParent)
    })
}

window.fixDropdownsInScrollContainer = fixDropdownsInScrollContainer
onReady(() => {fixDropdownsInScrollContainer(document.querySelector(".table-container"), document.querySelector("#page-content"))})
