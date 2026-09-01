// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* This script will be included on all pages with forms.
 * It adds a form handler warning when a form was modified when a tab is being closed,
 * and deactivates submit button in order to prevent accidental double submits.
 */

/**
 * Smoothly show or hide a block-level element. The target should have
 * class="collapse", which prevents a flash during first paint before
 * the script has loaded.
 *
 * ``.collapse`` forces ``display: block``, so if the content needs a
 * different display mode (e.g. ``.alert`` is flex), wrap it in a plain
 * ``<div class="collapse">`` and let the original element keep its own
 * classes.
 */
const setBlockVisibility = (target, visible) => {
    if (!target) return
    if (typeof target === "string") {
        document
            .querySelectorAll(target)
            .forEach((el) => setBlockVisibility(el, visible))
        return
    }
    target.classList.toggle("show", !!visible)
}

const isInDeletedFormsetRow = (element) => {
    const row = element.closest("[data-formset-form]")
    if (!row) return false
    return (
        row.hasAttribute("data-formset-form-deleted") ||
        !!row.querySelector("input[name$='-DELETE']:checked")
    )
}

const getFirstServerError = () => {
    for (const link of document.querySelectorAll(".error-summary a[href^='#']")) {
        const target = document.getElementById(link.getAttribute("href").slice(1))
        if (target && !isInDeletedFormsetRow(target)) return target
    }
    for (const element of document.querySelectorAll("[aria-invalid=true]")) {
        if (!isInDeletedFormsetRow(element)) return element
    }
}

const initInvalidHandling = () => {
    let handledInvalid = false
    document.addEventListener("invalid", (event) => {
        if (handledInvalid) return
        handledInvalid = true
        window.setTimeout(() => { handledInvalid = false }, 0)

        // Auto-focus is fine here, as it happens as a response to a user action
        scrollToField(event.target, { focus: true })
    }, true)
}

const initErrorSummary = () => {
    document.querySelectorAll(".error-summary a[href^='#']").forEach((link) => {
        link.addEventListener("click", (event) => {
            const target = document.getElementById(link.getAttribute("href").slice(1))
            if (!target) return
            event.preventDefault()
            scrollToField(target, { focus: true })
        })
    })
}

/**
 * Set a button to loading state with spinner. Returns a function to restore it to its regular state.
 */
const setButtonLoading = (button) => {
    const originalContent = button.innerHTML
    const originalDisabled = button.disabled
    button.innerHTML = `<i class="fa fa-cog animate-spin pr-0"></i> ${button.textContent}`
    button.disabled = true
    return () => {
        button.innerHTML = originalContent
        button.disabled = originalDisabled
    }
}

const originalData = new Map()
const handleUnload = (e) => {
    for (const form of originalData.keys()) {
        if (isDirty(form)) {
            e.preventDefault()
            return
        }
    }
}

const isDirty = (form) => {
    if (!!!form) return false
    const original = originalData.get(form)
    if (!original || Object.keys(original).length === 0) return false
    const currentData = {}
    new FormData(form).forEach((value, key) => (currentData[key] = value))
    for (const key in currentData) {
        if (JSON.stringify(currentData[key]) !== JSON.stringify(original[key])) {
            return true
        }
    }
    return false
}


const updateDirtyState = (form) => {
    const dirty = isDirty(form)
    form.querySelectorAll(".submit-group").forEach((group) => {
        group.classList.toggle("is-dirty", dirty)
    })
}

const initDiscardButtons = (form) => {
    form.querySelectorAll(".submit-group-discard").forEach((button) => {
        button.addEventListener("click", () => {
            window.removeEventListener("beforeunload", handleUnload)
            window.location.reload()
        })
    })
}

// Make sure the main form doesn't have unsaved changes before leaving
const initFormChanges = (form) => {
    // Populate original data after a short delay to make sure the form is fully loaded
    // and that any script interactions have run
    setTimeout(() => {
        const data = {}
        new FormData(form).forEach((value, key) => (data[key] = value))
        originalData.set(form, data)
    }, 1000)

    form.addEventListener("submit", () => {
        window.removeEventListener("beforeunload", handleUnload)
    })
    window.addEventListener("beforeunload", handleUnload)

    const onChange = () => updateDirtyState(form)
    form.addEventListener("input", onChange)
    form.addEventListener("change", onChange)
    initDiscardButtons(form)
}

const initStickySubmitGroup = (group) => {
    if (group.dataset.stickyInit) return
    group.dataset.stickyInit = "1"

    const sentinel = document.createElement("div")
    sentinel.className = "submit-group-sentinel"
    sentinel.setAttribute("aria-hidden", "true")
    group.after(sentinel)

    let root = group.parentElement
    while (root && root !== document.body) {
        const overflow = window.getComputedStyle(root).overflowY
        if (overflow === "auto" || overflow === "scroll") break
        root = root.parentElement
    }
    if (root === document.body) root = null

    const observer = new IntersectionObserver(
        ([entry]) => group.classList.toggle("is-floating", !entry.isIntersecting),
        { root, threshold: 0 },
    )
    observer.observe(sentinel)
}

const initFormButton = (form) => {
    if (form.dataset.submitProtection) return
    form.dataset.submitProtection = "true"
    const submitButtons = Array.from(form.querySelectorAll("button")).filter(
        (button) => button.type === "submit",  // checking property, not attribute, because minifiers strip default attrs
    )
    submitButtons.forEach(submitButton => {
        const submitButtonText = submitButton.textContent
        let lastSubmit = 0
        form.addEventListener("submit", () => {
            // We can't disable the button immediately, because then, the browser will
            // not send the button's value to the server. Instead, we'll just delay the
            // disabling a bit.
            submitButton.innerHTML = `<i class="fa fa-cog animate-spin pr-0"></i> ${submitButtonText}`
            lastSubmit = Date.now()
            setTimeout(() => {
                submitButton.classList.add("disabled")
            }, 1)
        })

        // If people submit the form, then navigate back with the back button,
        // the button will still be disabled.
        // We can’t fix this on page load, because the browser will not actually load
        // the page again, and we can’t fix it via a single timeout, because that might
        // take place while we’re away from the page.
        // So instead, we’ll check periodically if the button is still disabled, and if
        // it’s been more than 5 seconds since the last submit, we’ll re-enable it.
        const checkButton = () => {
            if (!form.isConnected) {
                window.clearInterval(intervalId)
                return
            }
            if (submitButton.classList.contains("disabled")) {
                if (Date.now() - lastSubmit > 5000) {
                    submitButton.classList.remove("disabled")
                    submitButton.innerHTML = submitButtonText
                }
            }
        }
        const intervalId = window.setInterval(checkButton, 1000)
    })
}


const initTextarea = (element, other, limit) => {
    const submitButtons = Array.from(element.form.querySelectorAll("button, input[type=submit]")).filter(button => !button.disabled && button.type === "submit")
    const buttonsWithName = submitButtons.filter(button => button.name.length > 0)
    if (submitButtons.length <= 1 && buttonsWithName.length === 0) {
        // We use classic form submit whenever we can, to be on the safe side
        element.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter" && ev.ctrlKey) {
                ev.preventDefault()
                // We need to remove the "are you sure" dialog that will show now otherwise
                window.removeEventListener("beforeunload", handleUnload)
                element.form.removeEventListener("submit", handleUnload)
                element.form.submit()
            }
        })
    } else {
        // But if there are multiple submit buttons, we click the first one,
        // to make sure the correct name/value is attached to the form data
        element.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter" && ev.ctrlKey) {
                ev.preventDefault()
                submitButtons[0].click()
            }
        })
    }
}

/* Register handlers */
onReady(() => {
    document
        .querySelectorAll("form[method=post]")
        .forEach((form) => {
            initFormChanges(form)
            initFormButton(form)
        })
    document.querySelectorAll("form textarea").forEach(element => initTextarea(element))
    document.querySelectorAll(".submit-group").forEach(initStickySubmitGroup)

    document.addEventListener("htmx:load", (event) => {
        const root = event.detail.elt
        if (!root?.querySelectorAll) return
        if (root.matches?.("form[method=post]")) initFormButton(root)
        root.querySelectorAll("form[method=post]").forEach(initFormButton)
    })

    initInvalidHandling()
    initErrorSummary()
    if (document.readyState === "complete") {
        scrollToField(getFirstServerError())
    } else {
        document.addEventListener("DOMContentLoaded", () => scrollToField(getFirstServerError()), { once: true })
    }

    document.querySelectorAll(".hide-optional").forEach((element) => {
        while (
            !element.classList.contains("form-group") &&
            element.nodeName !== "BODY"
        ) {
            element = element.parentElement
        }
        if (element.nodeName === "BODY") return
        element.querySelector(".optional")?.classList.add("d-none")
    })
})
