/* Copyright 2023 Your Company */
odoo.define('3cx_connector.screen_pop', function (require) {
    "use strict";

    // Required imports
    const { Notification } = require('web.Notification');
    const { patch } = require('web.utils');
    const core = require('web.core');
    const _t = core._t;
    const rpc = require('web.rpc');

    // Patch the Notification widget to add 3CX screen pop functionality
    patch(Notification.prototype, '3cx_screen_pop_notification', {
        /**
         * Override _render to handle 3CX screen pop notifications
         */
        _render: function() {
            if (this.notification.type === '3cx_screen_pop') {
                this._render3cxPopup();
            } else {
                this._super.apply(this, arguments);
            }
        },

        /**
         * Render the 3CX-specific notification popup
         */
        _render3cxPopup: function() {
            this.$el.addClass('o_3cx_screen_pop');
            this.$el.html(core.qweb.render('3cx_connector.screen_pop_template', {
                notification: this.notification
            }));
            this._bindCallBackButton();
            this._bindCloseButton();
        },

        /**
         * Bind click handler to the call back button
         */
        _bindCallBackButton: function() {
            const self = this;
            this.$el.find('.o_3cx_call_back').on('click', function() {
                self._makeCall(self.notification.data.phone);
            });
        },

        /**
         * Bind click handler to the close button
         */
        _bindCloseButton: function() {
            const self = this;
            this.$el.find('.o_notification_close').on('click', function() {
                self.destroy();
            });
        },

        /**
         * Initiate a call through 3CX
         * @param {String} phoneNumber 
         */
        _makeCall: function(phoneNumber) {
            const self = this;
            rpc.query({
                model: 'pbx.config',
                method: 'make_call',
                args: [phoneNumber],
            }).then(function(result) {
                if (result && result.params) {
                    self.call('notification_service', 'notify', result.params);
                }
            }).catch(function(error) {
                self.call('notification_service', 'notify', {
                    title: _t('Call Failed'),
                    message: error.data.message || _t('Could not initiate call'),
                    type: 'danger',
                    sticky: true
                });
            });
        }
    });

    // Set up 3CX message listener when web client is ready
    core.bus.on('web_client_ready', null, function() {
        // Listen for messages from 3CX browser extension
        window.addEventListener('message', function(event) {
            if (event.data.type === '3cx_screen_pop') {
                _handle3cxEvent(event.data);
            }
        });

        // Alternative method: Check localStorage for call data
        setInterval(_checkLocalStorage, 1000);
    });

    /**
     * Handle incoming 3CX screen pop event
     * @param {Object} eventData 
     */
    function _handle3cxEvent(eventData) {
        core.bus.trigger('notification', {
            type: '3cx_screen_pop',
            title: _t('Incoming Call from %s').replace('%s', eventData.partner_name || eventData.phone),
            message: '',
            sticky: true,
            data: {
                partner_name: eventData.partner_name,
                partner_image: eventData.partner_image,
                phone: eventData.phone,
                company: eventData.company,
                redirect_url: eventData.redirect_url
            }
        });

        // Auto-open contact if enabled in system parameters
        const autoOpen = core.bus.parameters.get('3cx_auto_open') || false;
        if (autoOpen && eventData.redirect_url) {
            _openContactForm(eventData.redirect_url);
        }
    }

    /**
     * Check localStorage for 3CX call data (fallback method)
     */
    function _checkLocalStorage() {
        const callData = localStorage.getItem('3cx_current_call');
        if (callData) {
            _handle3cxEvent(JSON.parse(callData));
            localStorage.removeItem('3cx_current_call');
        }
    }

    /**
     * Open contact form in Odoo
     * @param {String} url 
     */
    function _openContactForm(url) {
        const action = {
            type: 'ir.actions.act_window',
            res_model: 'res.partner',
            views: [[false, 'form']],
            target: 'current',
            res_id: parseInt(url.match(/id=(\d+)/)[1])
        };
        core.bus.trigger('do_action', action);
    }
});