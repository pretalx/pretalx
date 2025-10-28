// SPDX-FileCopyrightText: 2023-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

let isFaved = false
let eventSlug = null
let submissionId = null
let favButton = null
let loggedIn = false
let apiBaseUrl = null
let setupRun = false

const getCookie = (name) => {
    let cookieValue = null
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";")
        for (var i = 0; i < cookies.length; i++) {
            let cookie = cookies[i].trim()
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === name + "=") {
                cookieValue = decodeURIComponent(
                    cookie.substring(name.length + 1),
                )
                break
            }
        }
    }
    return cookieValue
}

const spinStar = (star) => {
    star.classList.add('animate-spin')
    setTimeout(() => {
        star.classList.remove('animate-spin')
    }, 400)
}

const updateButton = (initial = false) => {
    // if "initial" is true, the star isn't animated
    if (isFaved && !favButton.querySelector('.fa-star').classList.contains('d-none')) return
    if (!isFaved && !favButton.querySelector('.fa-star-o').classList.contains('d-none')) return

    let active = '.fa-star'
    let inactive = '.fa-star'

    isFaved ? inactive = '.fa-star-o' : active = '.fa-star-o'
    favButton.querySelector(active).classList.remove('d-none')
    favButton.querySelector(inactive).classList.add('d-none')
    if (!initial) spinStar(favButton.querySelector(active))
}

const loadLocalFavs = () => {
    const data = localStorage.getItem(`${eventSlug}_favs`)
    let favs = []
	if (data) {
		try {
            favs = JSON.parse(data)
		} catch {
			localStorage.setItem(`${eventSlug}_favs`, '[]')
		}
	}
    return favs
}

const apiFetch = async (path, method) => {
    const headers = {'Content-Type': 'application/json'}
    if (method === 'POST' || method === 'DELETE') {
        headers['X-CSRFToken'] = getCookie('pretalx_csrftoken')
    }
    const response = await fetch(apiBaseUrl + path, {
        method,
        headers,
        credentials: 'same-origin',
    })
    return response.json()
}

const loadIsFaved = async () => {
    if (loggedIn) {
        return await apiFetch(`submissions/favourites/`, 'GET').then(data => {
            return data.includes(submissionId)
        }).catch(() => {return loadLocalFavs().includes(submissionId)})
    }
    return loadLocalFavs().includes(submissionId)
}

const saveLocalFavs = () => {
    let favs = loadLocalFavs()
    if (isFaved && !favs.includes(submissionId)) {
        favs.push(submissionId)
    } else if (!isFaved && favs.includes(submissionId)) {
        favs = favs.filter(id => id !== submissionId)
    }
    localStorage.setItem(`${eventSlug}_favs`, JSON.stringify(favs))
}

const toggleFavState = async () => {
    isFaved = !isFaved
    saveLocalFavs()
    updateButton()
    if (loggedIn) {
        await apiFetch(`submissions/${submissionId}/favourite/`, isFaved ? 'POST' : 'DELETE').catch()
    }
}

const pageSetup = async () => {
    setupRun = true
    eventSlug = window.location.pathname.split('/')[1]
    submissionId = window.location.pathname.split('/')[3]
    loggedIn = document.querySelector('#pretalx-messages').dataset.loggedIn === 'true'
    apiBaseUrl = window.location.origin + '/api/events/' + eventSlug + '/'

    isFaved = await loadIsFaved()
    favButton = document.getElementById('fav-button')
    favButton.addEventListener('click', toggleFavState)
    favButton.classList.remove('d-none')
    updateButton(true)

    if (loggedIn) saveLocalFavs()
}

onReady(pageSetup)
setTimeout(() => { if (!setupRun) pageSetup() }, 500)
