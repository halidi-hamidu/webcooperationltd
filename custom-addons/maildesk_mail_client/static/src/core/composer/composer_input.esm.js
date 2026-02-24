// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Composer Input.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { Component, markup, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { localization } from "@web/core/l10n/localization";
import { FileInput } from "@web/core/file_input/file_input";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { HtmlMailField } from "@mail/views/web/fields/html_mail_field/html_mail_field";
import { EmailInputField } from "../../components/fields/email_input/email_input_field.esm.js";

/**
 * ComposerInput - The form/editor portion of the composer.
 * Pattern mirrored from Odoo Mail: odoo/addons/mail/static/src/core/common/composer.js
 *
 * CRITICAL: Editor content is synced to ComposerRecord.body on every change.
 * This ensures content survives fold/unfold/navigation.
 */

export class ComposerInput extends Component {
    static template = "maildesk_mail_client.ComposerInput";
    static components = { FileInput, Wysiwyg, EmailInputField };
    static props = {
        composer: { type: Object }, // ComposerRecord
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.composerService = useService("maildesk.composer");

        // Local UI-only state (loading indicators)
        this.uiState = useState({
            sending: false,
        });

        // Auto-save interval
        this._autoSaveInterval = null;
        this._lastSavedState = null;
        this._sigObserver = null;

        onMounted(() => {
            this._autoSaveInterval = setInterval(() => this.saveDraft(), 60000);
        });

        onWillUnmount(() => {
            // Sync content before unmount to ensure nothing is lost
            this._syncEditorToRecord();
            if (this._autoSaveInterval) {
                clearInterval(this._autoSaveInterval);
            }
            if (this._sigObserver) {
                this._sigObserver.disconnect();
                this._sigObserver = null;
            }
        });
    }





    get composer() {
        return this.props.composer;
    }

    get accounts() {
        return this.composer.accounts || [];
    }

    /**
     * Wysiwyg config - Pattern mirrored from Odoo Mail.
     * CRITICAL: Uses composer.body as initial content.
     * Content is restored from record on every mount.
     */
    get wysiwygConfig() {
        return {
            content: markup(this.composer.body || ""),
            dropImageAsAttachment: true,
            classList: ["o_wysiwyg_content"],
            direction: localization.direction || "ltr",
            dynamicPlaceholder: true,
            disableFloatingToolbar: false,
            // Odoo core html_field injects `getRecordInfo` into the editor config.
            // Custom Wysiwyg configs must provide it too (Enterprise AI ChatGPTPlugin calls it).
            getRecordInfo: () => {
                const { model, resId, id } = this.composer;
                return { resModel: model, resId, data: {}, fields: {}, id };
            },
        };
    }


    // FIELD HANDLERS (delegate to record)


    addEmail = (entry, field) => {
        this.composer.addRecipient(entry, field);
    };

    removeEmail = (email, field) => {
        this.composer.removeRecipient(email, field);
    };

    toggleCc = () => {
        this.composer.toggleCc();
    };

    toggleBcc = () => {
        this.composer.toggleBcc();
    };

    onSubjectChange = (ev) => {
        this.composer.subject = ev.target.value;
    };

    onFromDisplayChange = (ev) => {
        this.composer.fromDisplay = ev.target.value;
    };

    async onAccountChange(ev) {
        const newAccountId = parseInt(ev.target.value);
        if (!newAccountId) return;

        this.composer.accountId = newAccountId;
        const acc = this.accounts.find(a => a.id === newAccountId);
        if (acc) {
            this.composer.fromDisplay = acc.sender_name || acc.name || "";
        }
        // FORCE RELOAD: Clear cached signature so _ensureSignatureLoaded fetches the new one
        this.composer.signatureHtml = undefined;
        await this.insertSignature(true);
    }


    /**
     * Called when editor loads. Sets up change listener.
     * CRITICAL: This is where we ensure content persists.
     */
    onEditorLoad = (editor) => {
        this.composer.wysiwygEditor = editor;

        // Pattern mirrored from Odoo Mail: listen for editor changes
        // Sync content to record on every meaningful change
        if (editor && editor.editable) {
            editor.editable.addEventListener("input", this._onEditorInput);
            editor.editable.addEventListener("paste", this._onEditorInput);
        }

        this._autoInsertSignature();
    };

    async _autoInsertSignature() {
        // Guard: already inserted
        if (this.composer._signatureInserted) return;

        // Validation loop: ensure editor is truly ready
        let editor = this.composer.wysiwygEditor;
        let attempts = 0;

        // Wait up to 1 second for editor.editable to be available if needed
        while ((!editor || !editor.editable) && attempts < 10) {
            await new Promise(r => setTimeout(r, 100));
            editor = this.composer.wysiwygEditor;
            attempts++;
        }

        if (!editor?.editable) {
            console.warn("[ComposerInput] Editor not ready for signature after wait.");
            return;
        }

        // Guard: signature available (lazy fetch allowed)
        await this._ensureSignatureLoaded();

        if (!this.composer.signatureHtml) {
            // Mark as inserted to avoid endless retries if no signature exists
            this.composer._signatureInserted = true;
            return;
        }

        // For reply/forward: blockquote may already exist OR body may be empty
        // We insert anyway — position logic handles placement
        const inserted = await this.insertSignature(false);

        if (inserted) {
            this.composer._signatureInserted = true;
        }
    }

    async _ensureSignatureLoaded() {
        if (this.composer.signatureHtml !== undefined) return;

        if (!this.composer.accountId) {
            this.composer.signatureHtml = "";
            return;
        }

        try {
            const res = await this.orm.searchRead(
                "mailbox.account",
                [["id", "=", this.composer.accountId]],
                ["signature"]
            );
            this.composer.signatureHtml = res?.[0]?.signature || "";
        } catch (e) {
            console.warn("Signature load failed:", e);
            this.composer.signatureHtml = "";
        }
    }

    /**
     * Sync editor content to ComposerRecord on input.
     * CRITICAL: This prevents content loss on fold/navigation.
     */
    _onEditorInput = () => {
        this._syncEditorToRecord();
    };

    /**
     * Sync current editor content to ComposerRecord.body.
     * Called on input, paste, and before unmount.
     */
    _syncEditorToRecord() {
        const editor = this.composer.wysiwygEditor;
        if (!editor || !editor.editable) return;

        try {
            // Get raw innerHTML for fast sync (not inlined, that's for save/send)
            const html = editor.editable.innerHTML || "";
            this.composer.body = html;
        } catch (e) {
            console.error("Failed to sync editor content:", e);
        }
    }

    /**
     * Get fully processed editor content for save/send.
     * Uses HtmlMailField.getInlinedEditorContent for proper email formatting.
     */
    async getEditorContent() {
        const editor = this.composer.wysiwygEditor;
        if (!editor || typeof editor.getElContent !== "function") {
            return this.composer.body || "";
        }
        try {
            const el = editor.getElContent();
            await HtmlMailField.getInlinedEditorContent(new WeakMap(), editor, el);
            return el.outerHTML;
        } catch (e) {
            console.error("getEditorContent failed:", e);
            return this.composer.body || "";
        }
    }

    async insertSignature(force = false) {
        const editor = this.composer.wysiwygEditor;
        if (!editor?.editable) return false;

        await this._ensureSignatureLoaded();
        const html = this.composer.signatureHtml;
        if (!html) return false;

        const root = editor.editable;

        // Remove existing signatures (outside quoted content)
        // Also remove the <br> immediately following the signature if present
        root.querySelectorAll(".o-maildesk-signature").forEach(n => {
            if (!n.closest(".o-maildesk-quoted-content")) {
                const next = n.nextSibling;
                if (next && next.nodeName === "BR") {
                    next.remove();
                }
                n.remove();
            }
        });

        const sig = document.createElement("div");
        sig.className = "o-maildesk-signature";
        sig.innerHTML = html;

        const br = document.createElement("br");

        const frag = document.createDocumentFragment();
        frag.appendChild(sig);
        frag.appendChild(br);

        const quotedContent = root.querySelector(".o-maildesk-quoted-content");

        if (quotedContent) {
            // Insert before quoted/forwarded content
            // Ensure there is a break before the signature if needed
            quotedContent.parentNode.insertBefore(frag, quotedContent);
        } else {
            // No quoted content - append at end (new compose)
            root.appendChild(frag);
        }

        this._syncEditorToRecord();
        return true;
    }


    // ATTACHMENTS


    onFileUploaded = (files) => {
        for (const file of files) {
            if (file.error) {
                this.notification.add(file.error, { title: _t("Upload error"), type: "danger" });
                continue;
            }
            this.composer.addAttachment({
                id: file.id,
                name: file.filename,
                mimetype: file.mimetype,
            });
        }
    };

    onFileRemove = (id) => {
        this.composer.removeAttachment(id);
    };

    getUrl(id) {
        const att = this.composer.attachments.find(a => a.id === id);
        if (att && att.access_token) {
            return `/web/content/${id}?access_token=${att.access_token}`;
        }
        return `/web/content/${id}`;
    }


    async saveDraft(manual = false) {
        const c = this.composer;

        // Sync and get processed content
        this._syncEditorToRecord();
        const htmlBody = await this.getEditorContent();
        c.body = htmlBody;

        const isEmpty =
            !htmlBody?.trim() &&
            !c.subject?.trim() &&
            !c.to.length &&
            !c.cc.length &&
            !c.bcc.length &&
            !c.attachments.length;

        if (isEmpty) return false;

        const payload = c.getDraftPayload();
        const currentState = JSON.stringify(payload);
        if (!manual && this._lastSavedState === currentState) return false;

        try {
            const draftId = await this.orm.call("mailbox.sync", "save_draft", [], payload);
            if (draftId) {
                c.draftMessageId = draftId;
            }
            this._lastSavedState = currentState;
            if (manual) {
                this.notification.add(_t("Draft saved"), { type: "success" });
            }
            return true;
        } catch (error) {
            console.error("Failed to save draft:", error);
            if (manual) {
                this.notification.add(_t("Failed to save draft"), { type: "danger" });
            }
            return false;
        }
    }

    saveDraftClick = async () => {
        await this.saveDraft(true);
    };

    sendMail = async () => {
        const c = this.composer;

        if (this.uiState.sending) return;

        const hasRecipients = c.to.length || c.cc.length || c.bcc.length;
        if (!hasRecipients) {
            this.notification.add(_t("Please add at least one recipient."), { type: "warning" });
            return;
        }
        if (!c.accountId) {
            this.notification.add(_t("Please choose the sending account."), { type: "warning" });
            return;
        }

        this.uiState.sending = true;
        c.status = "sending";

        try {
            // Sync and capture content
            this._syncEditorToRecord();
            const htmlBody = await this.getEditorContent();
            c.body = htmlBody;

            // Save draft first (without closing)
            await this.saveDraft(false);

            const payload = c.getSendPayload();
            await this.orm.call("mailbox.sync", "send_email", [], payload);

            c.status = "sent";

            // Callback if provided
            if (c._onSent) {
                c._onSent();
            }

            // Close composer on success
            this.composerService.closeComposer(c.id);

        } catch (e) {
            console.error("Failed to send:", e);
            c.status = "error";
            c.error = e.message || _t("Failed to send email.");
            const msg = e?.data?.message || e.message || _t("Failed to send email.");
            this.notification.add(msg, { type: "danger" });
        } finally {
            this.uiState.sending = false;
        }
    };

    insertSignatureClick = async () => {
        const ok = await this.insertSignature(true);
        if (ok) this.composer._signatureInserted = true;
    };
}
