// SPDX-FileCopyrightText: 2022-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const getReviewMapping = () => {
    const el = document.getElementById('review-mapping')
    if (!el) return null
    try {
        return JSON.parse(el.textContent)
    } catch (e) {
        console.error('Failed to parse review mapping data:', e)
        return null
    }
}

const addReviewDataToSelect = (select, reviewMapping) => {
    const fieldName = select.name
    const urlParams = new URLSearchParams(window.location.search)
    const direction = urlParams.get('direction') || 'reviewer'
    let entityId = null

    if (direction === 'reviewer') {
        const entityCode = fieldName.replace('reviewer-', '')
        entityId = reviewMapping.reviewer_code_to_id[entityCode]
    } else {
        const entityCode = fieldName.replace('submission-', '')
        entityId = reviewMapping.submission_code_to_id[entityCode]
    }

    if (!entityId) return

    Array.from(select.options).forEach(option => {
        const optionId = parseInt(option.value)
        if (!optionId) return

        let hasReview = false
        if (direction === 'reviewer') {
            hasReview = reviewMapping.reviewer_to_submissions[entityId] &&
                      reviewMapping.reviewer_to_submissions[entityId].includes(optionId)
        } else {
            hasReview = reviewMapping.submission_to_reviewers[entityId] &&
                      reviewMapping.submission_to_reviewers[entityId].includes(optionId)
        }

        if (hasReview && !option.text.includes('✓')) {
            option.text += ' ✓'
            option.setAttribute('data-highlight', 'true')
        }
    })
}

const addReviewData = () => {
    const reviewMapping = getReviewMapping()
    if (!reviewMapping) return

    document.querySelectorAll('select.enhanced').forEach(select => {
        if (select._choicesInstance) select._choicesInstance.destroy()
        addReviewDataToSelect(select, reviewMapping)
        initSelect(select)
    })
}

document.addEventListener("htmx:load", (event) => {
    const loaded = event.detail.elt
    if (!loaded.classList?.contains('assignment-field-wrapper')) return
    const select = loaded.querySelector('select.enhanced')
    if (!select) return
    const reviewMapping = getReviewMapping()
    if (!reviewMapping) return
    addReviewDataToSelect(select, reviewMapping)
    initSelect(select)
})

onReady(() => {
    document
        .querySelector("#direction select")
        .addEventListener("change", (e) => {
            e.target.form.submit()
        })

    addReviewData()
})
