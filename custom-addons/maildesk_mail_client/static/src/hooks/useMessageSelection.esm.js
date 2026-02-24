// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Usemessageselection.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * useMessageSelection Hook
 *
 * Manages message selection state with shift-click range selection.
 * Extracted from maildesk.esm.js to be reusable.
 *
 * Usage:
 *   const { selectedKeys, toggleSelection, selectRange, clearSelection, selectAll } = useMessageSelection();
 */

import { useState } from "@odoo/owl";

export function useMessageSelection() {
    const state = useState({
        selectedKeys: new Set(),
        shiftAnchorKey: null,
    });

    const toggleSelection = (msgKey, isShift = false, isCtrl = false, allMessages = []) => {
        if (isShift && state.shiftAnchorKey) {
            // Range select from anchor to current
            const anchorIdx = allMessages.findIndex(m => m.msg_key === state.shiftAnchorKey);
            const currentIdx = allMessages.findIndex(m => m.msg_key === msgKey);

            if (anchorIdx >= 0 && currentIdx >= 0) {
                const [start, end] = [anchorIdx, currentIdx].sort((a, b) => a - b);
                const rangeKeys = allMessages.slice(start, end + 1).map(m => m.msg_key);
                state.selectedKeys = new Set(rangeKeys);
            }
        } else if (isCtrl) {
            // Toggle single
            if (state.selectedKeys.has(msgKey)) {
                state.selectedKeys.delete(msgKey);
            } else {
                state.selectedKeys.add(msgKey);
            }
            state.selectedKeys = new Set(state.selectedKeys); // Trigger reactivity
        } else {
            // Single select (replace)
            state.selectedKeys = new Set([msgKey]);
            state.shiftAnchorKey = msgKey;
        }
    };

    const clearSelection = () => {
        state.selectedKeys = new Set();
        state.shiftAnchorKey = null;
    };

    const selectAll = (allMessages = []) => {
        state.selectedKeys = new Set(allMessages.map(m => m.msg_key));
    };

    const isSelected = (msgKey) => state.selectedKeys.has(msgKey);

    return {
        selectedKeys: state.selectedKeys,
        toggleSelection,
        clearSelection,
        selectAll,
        isSelected,
        get count() { return state.selectedKeys.size; },
    };
}
