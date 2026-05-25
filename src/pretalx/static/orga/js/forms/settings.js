// SPDX-FileCopyrightText: 2024-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

onReady(() => {
    const dateHelpText = document.getElementById("id_date_to_helptext")
    const dateTo = document.getElementById("id_date_to")
    const dateFrom = document.getElementById("id_date_from")
    if (dateHelpText && dateTo && dateFrom) {
        const showDateHelpText = () => {
            dateHelpText.classList.remove("d-none")
        }
        dateHelpText.classList.add("d-none")
        dateTo.addEventListener("change", showDateHelpText)
        dateFrom.addEventListener("change", showDateHelpText)
    }

    const attendeeSignupToggle = document.getElementById("id_attendee_signup")
    const presentMultipleTimesToggle = document.getElementById(
        "id_present_multiple_times",
    )
    const attendeeSignupDependents = document.querySelector(
        "#attendee-signup-fieldset .attendee-signup-dependent",
    )

    if (
        !attendeeSignupToggle ||
        !presentMultipleTimesToggle ||
        !attendeeSignupDependents
    ) {
        return
    }

    const updateAttendeeSignupVisibility = () => {
        setBlockVisibility(attendeeSignupDependents, attendeeSignupToggle.checked)
    }

    // Attendee signup and multi-slot scheduling are mutually exclusive, so
    // we mirror the server-side validator here so the user doesn’t run into
    // avoidable form errors.
    const updateSignupMultiSlotExclusion = () => {
        presentMultipleTimesToggle.disabled = attendeeSignupToggle.checked
        attendeeSignupToggle.disabled = presentMultipleTimesToggle.checked
    }

    attendeeSignupToggle.addEventListener("change", () => {
        updateAttendeeSignupVisibility()
        updateSignupMultiSlotExclusion()
    })
    presentMultipleTimesToggle.addEventListener(
        "change",
        updateSignupMultiSlotExclusion,
    )
    updateAttendeeSignupVisibility()
    updateSignupMultiSlotExclusion()
})
