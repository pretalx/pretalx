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
            document.querySelector(
                "#id_question_required input[value=required]",
            ).checked,
    )
    setBlockVisibility("#limit-length", variant === "text" || variant === "string")
    setBlockVisibility("#limit-number", variant === "number")
    setBlockVisibility("#limit-date", variant === "date")
    setBlockVisibility("#limit-datetime", variant === "datetime")
    setBlockVisibility("#limit-options", variant === "multiple_choice")
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

onReady(() => {
    document
        .querySelector("#id_variant")
        .addEventListener("change", question_page_toggle_view)
    document
        .querySelectorAll("#id_question_required input")
        .forEach((e) => e.addEventListener("change", question_page_toggle_view))
    document
        .querySelectorAll("#id_question_required input")
        .forEach((e) =>
            e.addEventListener("change", question_page_toggle_deadline),
        )
    document
        .querySelector("#id_is_public")
        .addEventListener("change", question_page_toggle_view)
    question_page_toggle_view()
    question_page_toggle_deadline()
})
