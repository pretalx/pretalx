// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

onReady(() => {
    const WORD_CHARACTER = /[\p{L}\p{N}]/u;
    // Align with Python definition of whitespace
    const WHITESPACE = '\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
    const WHITESPACE_RUN = new RegExp(`[${WHITESPACE}]+`, 'g');
    const SURROUNDING_WHITESPACE = new RegExp(`^[${WHITESPACE}]+|[${WHITESPACE}]+$`, 'g');
    const LEADING_WHITESPACE = new RegExp(`^[${WHITESPACE}]*`);
    const TOKEN = new RegExp(`[^${WHITESPACE}]+`, 'g');

    const normalizeLineBreaks = (text) => text.replace(/\r\n/g, '\n');
    const trimWhitespace = (text) => text.replace(SURROUNDING_WHITESPACE, '');

    const countLength = (value, countIn) => {
        // Keep word counting in sync with pretalx.cfp.forms.count_length
        const normalized = trimWhitespace(normalizeLineBreaks(value));
        if (countIn === 'words') {
            return normalized.split(WHITESPACE_RUN).filter((token) => WORD_CHARACTER.test(token)).length;
        }
        // Align with Python counting: count code points rather than UTF-16 units
        return [...normalized].length;
    };

    const excessIndex = (normalized, countIn, max) => {
        if (countIn !== 'words') {
            // It's complicated: we need to walk by code point so we never try to start highlighting
            // inside a surrogate pair.
            let index = normalized.match(LEADING_WHITESPACE)[0].length;
            for (let counted = 0; counted < max && index < normalized.length; counted += 1) {
                index += normalized.codePointAt(index) > 0xffff ? 2 : 1;
            }
            return index;
        }
        let words = 0;
        for (const match of normalized.matchAll(TOKEN)) {
            if (!WORD_CHARACTER.test(match[0])) continue;
            words += 1;
            if (words === max) return match.index + match[0].length;
        }
        return normalized.length;
    };

    const escapeHtml = (text) => {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    const createWrapper = (element, wrapperClass, elementClass) => {
        const parentEl = element.closest('.form-group') || element.parentElement;
        let wrapper = parentEl.querySelector(`.${wrapperClass}`);

        if (!wrapper) {
            wrapper = document.createElement('div');
            wrapper.className = wrapperClass;
            element.parentElement.insertBefore(wrapper, element);
            wrapper.appendChild(element);
            if (elementClass) {
                element.classList.add(elementClass);
            }
        }
        return wrapper;
    };

    const updateCounter = (element, current, min, max) => {
        const isTextarea = element.tagName === 'TEXTAREA';
        const wrapperClass = isTextarea ? 'character-limit-highlight-wrapper' : 'character-limit-input-wrapper';
        const counterParent = element.closest(`.${wrapperClass}`);
        let counter = counterParent?.querySelector('.character-counter');

        if (!counter) {
            counter = document.createElement('div');
            const counterType = isTextarea ? 'textarea' : 'input';
            counter.className = `character-counter character-counter-${counterType} text-small`;
            counterParent?.appendChild(counter);
        }

        const belowMin = min && current > 0 && current < min;
        const target = belowMin ? min : max;
        const showCounter = belowMin || (max && current >= max * 0.8);

        counter.classList.toggle('text-danger', !belowMin);
        counter.classList.toggle('text-muted', !!belowMin);
        counter.style.display = showCounter ? 'block' : 'none';
        if (showCounter) {
            counter.textContent = `${current}/${target}`;
        }
    };

    // We only clear our own flags
    const flaggedInvalid = new WeakSet();

    const updateValidationState = (element, isInvalid) => {
        if (isInvalid) {
            element.setAttribute('aria-invalid', 'true');
            flaggedInvalid.add(element);
            element.classList.add('is-invalid');
        } else {
            if (flaggedInvalid.delete(element)) {
                element.removeAttribute('aria-invalid');
            }
            element.classList.remove('is-invalid');
        }
    };

    const HIGHLIGHT_STYLES = [
        'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
        'font-family', 'font-size', 'font-weight', 'font-style',
        'line-height', 'letter-spacing', 'word-spacing',
        'border-width', 'box-sizing',
    ];

    const updateHighlight = (element, normalized, index) => {
        const isTextarea = element.tagName === 'TEXTAREA';
        const highlightWrapper = createWrapper(
            element,
            isTextarea ? 'character-limit-highlight-wrapper' : 'character-limit-input-wrapper',
            isTextarea ? 'character-limit-textarea' : 'character-limit-input',
        );
        const highlightClass = isTextarea ? 'character-limit-highlight' : 'character-limit-highlight-input';
        let highlightDiv = highlightWrapper.querySelector(`.${highlightClass}`);

        if (!highlightDiv) {
            highlightDiv = document.createElement('div');
            highlightDiv.className = highlightClass;
            highlightWrapper.insertBefore(highlightDiv, element);

            // Copy computed styles for reliable alignment
            const computedStyle = window.getComputedStyle(element);
            HIGHLIGHT_STYLES.forEach(style => {
                highlightDiv.style[style] = computedStyle[style];
            });

            // Sync scrolling
            element.addEventListener('scroll', () => {
                if (isTextarea) highlightDiv.scrollTop = element.scrollTop;
                highlightDiv.scrollLeft = element.scrollLeft;
            });
        }

        if (index < 0) {
            highlightDiv.style.display = 'none';
            return;
        }
        highlightDiv.innerHTML =
            escapeHtml(normalized.substring(0, index)) +
            '<mark class="character-limit-excess">' + escapeHtml(normalized.substring(index)) + '</mark>';
        highlightDiv.style.display = 'block';
        highlightDiv.scrollLeft = element.scrollLeft;
    };

    const validateField = (element) => {
        const countIn = element.dataset.countIn === 'words' ? 'words' : 'chars';
        const minLength = parseInt(element.dataset.minlength, 10) || 0;
        const maxLength = parseInt(element.dataset.maxlength, 10) || 0;
        if (!minLength && !maxLength) return;

        const normalized = normalizeLineBreaks(element.value);
        const current = countLength(element.value, countIn);
        const isOverLimit = !!maxLength && current > maxLength;

        if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
            updateHighlight(element, normalized, isOverLimit ? excessIndex(normalized, countIn, maxLength) : -1);
        }
        updateCounter(element, current, minLength, maxLength);
        updateValidationState(element, isOverLimit);
    };

    const initializeField = (element) => {
        // maxlength silently truncates, breaking paste behaviour
        if (element.dataset.maxlength && element.hasAttribute('maxlength')) {
            element.removeAttribute('maxlength');
        }
        validateField(element);
        ['input', 'change', 'paste'].forEach(eventType => {
            element.addEventListener(eventType, () => {
                // Small delay for paste events to allow content to be inserted
                setTimeout(() => validateField(element), 0);
            });
        });
    };

    document.querySelectorAll('[data-maxlength], [data-minlength]').forEach(initializeField);
})
