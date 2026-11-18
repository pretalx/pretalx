// Fills in and locks title, abstract and description when a core session type
// is chosen in the CfP form. The server overwrites these fields on save anyway
// (signals.enforce_fixed_content); this only shows the speaker what they get.
(() => {
    const FIELDS = ["title", "abstract", "description"]

    const init = () => {
        const dataElement = document.getElementById("fixed-sessions-data")
        const meta = document.querySelector('meta[name="fixed-sessions"]')
        const title = document.getElementById("id_title")
        if (!dataElement || !meta || !title) return
        const fixed = JSON.parse(dataElement.textContent)
        const inputs = FIELDS.map((name) => [name, document.getElementById(`id_${name}`)]).filter(
            ([, input]) => input,
        )
        // Missing when the form has only one session type or it can't change
        const select = document.getElementById("id_submission_type")

        const notice = document.createElement("div")
        notice.className = "alert alert-info"
        notice.textContent = meta.dataset.notice
        notice.hidden = true
        const anchor = title.closest(".form-group") || title
        anchor.parentNode.insertBefore(notice, anchor)

        // The type whose content is currently in the fields
        let applied = null
        const update = () => {
            const type = select ? select.value : meta.dataset.currentType
            const content = fixed[type]
            if (content) {
                for (const [name, input] of inputs) {
                    input.value = content[name] || ""
                    input.readOnly = true
                    input.dispatchEvent(new Event("input", { bubbles: true }))
                }
                applied = type
            } else if (applied) {
                // Leaving a core type: clear its text, keep anything else
                for (const [name, input] of inputs) {
                    if (input.value === (fixed[applied][name] || "")) input.value = ""
                    input.readOnly = false
                    input.dispatchEvent(new Event("input", { bubbles: true }))
                }
                applied = null
            }
            notice.hidden = !content
        }

        if (select) select.addEventListener("change", update)
        update()
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init)
    else init()
})()
