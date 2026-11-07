// SPDX-FileCopyrightText: 2022-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const question_page_toggle_view = () => {
    const variant = document.querySelector("#id_variant").value
    const isPublic = document.querySelector("#id_is_public").checked

    setBlockVisibility(
        "#answer-options",
        variant === "choices" || variant === "multiple_choice",
    )
    setBlockVisibility(
        "#alert-required-boolean",
        variant === "boolean" &&
            document.querySelector("#id_question_required input[value=required]")
                .checked,
    )
    setBlockVisibility("#limit-length", variant === "text" || variant === "string")
    setBlockVisibility("#limit-number", variant === "number")
    setBlockVisibility("#limit-date", variant === "date")
    setBlockVisibility("#limit-datetime", variant === "datetime")
    setBlockVisibility("#limit-options", variant === "multiple_choice")
    setBlockVisibility("#limit-file", variant === "file")
    setBlockVisibility("#icon-field", variant === "url" && isPublic)
    setBlockVisibility("#limit-teams", !isPublic)
}

const question_page_toggle_deadline = () => {
    const deadline = document.querySelector("#id_deadline")
    const deadlineWrapper = document.querySelector("#deadline-wrapper")
    const deadlineRequired = document.querySelector("#id_question_required_2")

    if (deadlineRequired.checked) {
        setBlockVisibility(deadlineWrapper, true)
        deadline.setAttribute("required", "required")
    } else {
        setBlockVisibility(deadlineWrapper, false)
        deadline.removeAttribute("required")
    }
}

const question_page_update_file_group = (group) => {
    const header = group.querySelector("[data-file-type-wildcard]")
    const members = [...group.querySelectorAll("[data-file-type-member]")]
    members.forEach((member) => {
        if (header.checked) member.checked = true
        member.disabled = header.checked || header.disabled
    })
    const checked = members.filter((member) => member.checked).length
    header.indeterminate = !header.checked && checked > 0
}

onReady(() => {
    document.querySelectorAll("[data-file-type-group]").forEach((group) => {
        group.addEventListener("change", (event) => {
            if (
                event.target.matches("[data-file-type-wildcard]") &&
                !event.target.checked
            ) {
                group
                    .querySelectorAll("[data-file-type-member]")
                    .forEach((member) => (member.checked = false))
            }
            question_page_update_file_group(group)
        })
        question_page_update_file_group(group)
    })
    document
        .querySelector("#id_variant")
        .addEventListener("change", question_page_toggle_view)
    document
        .querySelectorAll("#id_question_required input")
        .forEach((e) => e.addEventListener("change", question_page_toggle_view))
    document
        .querySelectorAll("#id_question_required input")
        .forEach((e) => e.addEventListener("change", question_page_toggle_deadline))
    document
        .querySelector("#id_is_public")
        .addEventListener("change", question_page_toggle_view)
    question_page_toggle_view()
    question_page_toggle_deadline()
})
