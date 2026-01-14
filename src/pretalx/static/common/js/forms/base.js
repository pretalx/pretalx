// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* This script will be included on all pages with forms.
 * It adds a form handler warning when a form was modified when a tab is being closed,
 * and deactivates submit button in order to prevent accidental double submits.
 */

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

const originalData = {}

const handleUnload = (e) => {
    const form = e.target.form
    if (isDirty(form)) {
        e.preventDefault()
    }
}

const isDirty = (form) => {
    if (!!!form) return false
    if (Object.keys(originalData[form.id]).length === 0) return false
    const currentData = {}
    new FormData(form).forEach((value, key) => (currentData[key] = value))
    /* We have to compare all the current form's fields individually, because
     * there may be multiple forms with no/the same ID on the page. */
    for (const key in currentData) {
        if (JSON.stringify(currentData[key]) !== JSON.stringify(originalData[form.id][key])) {
            return true
        }
    }
    return false
}


// Make sure the main form doesn't have unsaved changes before leaving
const initFormChanges = (form) => {
    // Populate original data after a short delay to make sure the form is fully loaded
    // and that any script interactions have run
    setTimeout(() => {
        originalData[form.id] = {}
        new FormData(form).forEach((value, key) => (originalData[form.id][key] = value))
    }, 1000)

    form.addEventListener("submit", () => {
        window.removeEventListener("beforeunload", handleUnload)
    })
    window.addEventListener("beforeunload", handleUnload)
}

const initFormButton = (form) => {
    form.querySelectorAll("button").forEach(submitButton => {
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
            if (submitButton.classList.contains("disabled")) {
                if (Date.now() - lastSubmit > 5000) {
                    submitButton.classList.remove("disabled")
                    submitButton.innerHTML = submitButtonText
                }
            }
        }
        window.setInterval(checkButton, 1000)
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
