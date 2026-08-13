// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Apply the collapsed sidebar state before first paint, so the rail does not
// flash open. The sidebar is expanded unless it was explicitly collapsed.
(function() {
    'use strict';

    try {
        if (localStorage.getItem('sidebarVisible') === '0') {
            document.documentElement.classList.add('sidebar-collapsed');
        }
    } catch (e) {
        // localStorage can be unavailable; expanded is the default anyway.
    }
})();
