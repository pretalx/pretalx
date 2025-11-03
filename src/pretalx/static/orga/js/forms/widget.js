// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

document
    .querySelector("button#generate-widget")
    .addEventListener("click", (event) => {
        document.querySelector("#widget-generation").classList.add("d-none")
        document.querySelector("#generated-widget").classList.remove("d-none")
        const secondPre = document.querySelector("pre#widget-body")
        secondPre.innerHTML = secondPre.innerHTML.replace(
            "LOCALE",
            document.querySelector("#id_locale").value,
        )
        secondPre.innerHTML = secondPre.innerHTML.replace(
            "FORMAT",
            document.querySelector("#id_schedule_display").value,
        )
        const days = Array.from(document.querySelector("#id_days").querySelectorAll("option:checked"),e=>e.value)
        const rooms = Array.from(document.querySelector("#id_rooms").querySelectorAll("option:checked"),e=>e.value)
        let dataFilter = ""
        if (days.length) {
            dataFilter += ` date-filter="${days.join(",")}"`
        }
        if (rooms.length) {
            dataFilter += ` room-filter="${rooms.join(",")}"`
        }
        secondPre.innerHTML = secondPre.innerHTML.replace("FILTER_DATA", dataFilter)
    })
