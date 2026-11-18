// Fills in and locks the fields a core session fixes (title, abstract,
// description, track, answers to proposal questions) in the CfP wizard and the
// speaker's edit page. The server overwrites them on save anyway
// (signals.py); this only shows the speaker what they get.
(() => {
    const TEXT_FIELDS = ["title", "abstract", "description"]

    const init = () => {
        const dataElement = document.getElementById("fixed-sessions-data")
        const meta = document.querySelector('meta[name="fixed-sessions"]')
        const form = document.querySelector("form[method=post]")
        if (!dataElement || !meta || !form) return
        const fixed = JSON.parse(dataElement.textContent)
        // Missing when the form has only one session type, it can't change,
        // or on later wizard steps
        const select = document.getElementById("id_submission_type")

        const inputsFor = (name) => [...form.querySelectorAll(`[name="${name}"]`)]
        const fieldsOf = (content) => {
            const fields = {}
            for (const name of TEXT_FIELDS) fields[name] = content[name] || ""
            if (content.track) fields.track = content.track
            Object.assign(fields, content.answers || {})
            return fields
        }

        const notice = document.createElement("div")
        notice.className = "alert alert-info"
        notice.textContent = meta.dataset.notice
        notice.hidden = true
        const first = form.querySelector(".form-group, fieldset, input:not([type=hidden])")
        if (first) first.parentNode.insertBefore(notice, first)

        // Radios and checkboxes can't be read-only; undo clicks on them instead
        const blockClick = (event) => event.preventDefault()
        // Selects can't be read-only either; put the fixed value back
        const restore = (event) => {
            event.target.value = event.target.dataset.fixedValue
        }

        const lock = (input, value) => {
            input.dataset.fixedSession = "1"
            if (input.type === "radio" || input.type === "checkbox") {
                const values = Array.isArray(value) ? value : [value]
                input.checked =
                    typeof value === "boolean" ? value : values.includes(input.value)
                input.addEventListener("click", blockClick)
            } else if (input.tagName === "SELECT") {
                const values = Array.isArray(value) ? value : [value]
                // The speaker's choice, put back when they leave the core type
                if (input.dataset.valueBeforeFixed === undefined) {
                    input.dataset.valueBeforeFixed = JSON.stringify(
                        [...input.selectedOptions].map((option) => option.value),
                    )
                }
                for (const option of input.options) option.selected = values.includes(option.value)
                input.dataset.fixedValue = input.value
                // pretalx's enhanced selects (track, long choice lists) are
                // Choices.js widgets drawn over the hidden select
                // (common/js/forms/select.js); update the widget too
                const choices = input._choicesInstance
                if (choices) {
                    choices.removeActiveItems()
                    choices.setChoiceByValue(values)
                }
                // inert, not disabled: a disabled select isn't submitted
                const container = input.closest(".choices")
                if (container) container.inert = true
                input.addEventListener("change", restore)
            } else {
                input.value = value
                input.readOnly = true
            }
            input.dispatchEvent(new Event("input", { bubbles: true }))
        }

        const unlock = (input) => {
            delete input.dataset.fixedSession
            input.removeEventListener("click", blockClick)
            input.removeEventListener("change", restore)
            input.readOnly = false
            const container = input.closest(".choices")
            if (container) container.inert = false
            if (input.dataset.valueBeforeFixed !== undefined) {
                const values = JSON.parse(input.dataset.valueBeforeFixed)
                delete input.dataset.valueBeforeFixed
                for (const option of input.options) option.selected = values.includes(option.value)
                const choices = input._choicesInstance
                if (choices) {
                    choices.removeActiveItems()
                    choices.setChoiceByValue(values)
                }
            }
        }

        let applied = null
        const update = () => {
            const type = select ? select.value : meta.dataset.currentType
            const content = fixed[type]
            if (applied && applied !== type) {
                // Leaving a core type: unlock, and clear its texts if unchanged
                for (const [name, value] of Object.entries(fieldsOf(fixed[applied]))) {
                    for (const input of inputsFor(name)) {
                        unlock(input)
                        if (TEXT_FIELDS.includes(name) && input.value === value) input.value = ""
                    }
                }
                applied = null
            }
            if (content) {
                for (const [name, value] of Object.entries(fieldsOf(content))) {
                    for (const input of inputsFor(name)) lock(input, value)
                }
                applied = type
            }
            notice.hidden = !content
        }

        if (select) select.addEventListener("change", update)
        update()
    }

    // After "load", so pretalx's own scripts have built their select widgets
    if (document.readyState === "complete") init()
    else window.addEventListener("load", init)
})()
