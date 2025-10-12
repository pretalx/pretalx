// SPDX-FileCopyrightText: 2022-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const addReviewData = () => {
    const reviewMappingElement = document.getElementById('review-mapping')
    if (!reviewMappingElement) return

    let reviewMapping = null
    try {
        reviewMapping = JSON.parse(reviewMappingElement.textContent)
    } catch (e) {
        console.error('Failed to parse review mapping data:', e)
        return
    }

    const enhancedSelects = document.querySelectorAll('select.enhanced')
    const urlParams = new URLSearchParams(window.location.search)
    const direction = urlParams.get('direction') || 'reviewer'

    enhancedSelects.forEach(select => {
        const fieldName = select.name
        let entityId = null

        if (direction === 'reviewer') {
            const entityCode = fieldName.replace('reviewer-', '')
            entityId = reviewMapping.reviewer_code_to_id[entityCode]
        } else {
            const entityCode = fieldName.replace('submission-', '')
            entityId = reviewMapping.submission_code_to_id[entityCode]
        }

        if (!entityId) return

        if (select._choicesInstance) {
            select._choicesInstance.destroy()
        }

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

        initSelect(select)
    })
}

onReady(() => {
    document
        .querySelector("#direction select")
        .addEventListener("change", (e) => {
            e.target.form.submit()
        })

    addReviewData()
})
