// SPDX-FileCopyrightText: 2017-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const handleFeaturedChange = (element) => {
    const resetStatus = () => {
        statusWrapper.querySelectorAll("i").forEach((element) => {
            element.classList.add("d-none")
        })
    }
    const setStatus = (statusName) => {
        resetStatus()
        statusWrapper.querySelector("." + statusName).classList.remove("d-none")
        setTimeout(resetStatus, 3000)
    }
    const fail = () => {
        element.checked = !element.checked
        setStatus("fail")
    }

    const id = element.dataset.id
    const statusWrapper = element.parentElement.parentElement
    setStatus("working")

    const url = window.location.pathname + id + "/toggle_featured"
    const options = {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("pretalx_csrftoken"),
        },
        credentials: "include",
    }

    fetch(url, options)
        .then((response) => {
            if (response.status === 200) {
                setStatus("done")
            } else {
                fail()
            }
        })
        .catch((error) => fail())
}

onReady(() => {
    document
        .querySelectorAll("input.submission-featured")
        .forEach((element) =>
            element.addEventListener("change", () =>
                handleFeaturedChange(element),
            ),
        )
})
