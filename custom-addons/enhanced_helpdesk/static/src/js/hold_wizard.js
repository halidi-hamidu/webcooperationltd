odoo.define('enhanced_helpdesk.hold_wizard', function (require) {
'use strict';

var FormView = require('web.FormView');
var Dialog = require('web.Dialog');
var core = require('web.core');

FormView.include({
    /**
     * Override to add auto-refresh functionality to hold wizard
     */
    _instantiateRenderer: function () {
        var renderer = this._super.apply(this, arguments);
        
        // Check if this is the hold wizard or confirmation wizard
        if (this.modelName === 'helpdesk.ticket.hold.wizard' || 
            this.modelName === 'helpdesk.hold.confirmation.wizard') {
            this._setupHoldWizardAutoRefresh(renderer);
        }
        
        return renderer;
    },
    
    /**
     * Setup auto-refresh for hold wizard
     */
    _setupHoldWizardAutoRefresh: function (renderer) {
        var self = this;
        
        if (!renderer || !renderer.state) return;
        
        // Add refresh on form interactions for hold wizard only
        if (this.modelName === 'helpdesk.ticket.hold.wizard') {
            renderer.on('field_changed', null, function() {
                self._debouncedRefresh();
            });
            
            // Auto-refresh every 15 seconds to keep data fresh
            if (this._holdWizardAutoRefreshInterval) {
                clearInterval(this._holdWizardAutoRefreshInterval);
            }
            
            this._holdWizardAutoRefreshInterval = setInterval(function() {
                if (self.renderer && self.renderer.state && !self.renderer.state.data.show_success_info) {
                    self._softRefreshWizard();
                }
            }, 15000);
        }
        
        // Enhanced dialog close listener for both wizards
        this._setupDialogCloseListener();
    },
    
    /**
     * Setup dialog close listener to refresh parent page
     */
    _setupDialogCloseListener: function() {
        var self = this;
        
        // Wait for DOM to be ready
        setTimeout(function() {
            var $modal = self.$el ? self.$el.closest('.modal') : null;
            
            if ($modal && $modal.length) {
                // Remove any existing listeners to avoid duplicates
                $modal.off('hidden.bs.modal.hold_wizard');
                
                // Add our custom listener
                $modal.on('hidden.bs.modal.hold_wizard', function() {
                    if (self.modelName === 'helpdesk.ticket.hold.wizard' || 
                        self.modelName === 'helpdesk.hold.confirmation.wizard') {
                        
                        // Close all modals first
                        $('.modal').modal('hide');
                        
                        // Force page refresh after a short delay
                        setTimeout(function() {
                            window.location.reload(true);
                        }, 200);
                    }
                });
            }
        }, 100);
    },
    
    /**
     * Override action execution to handle our custom actions
     */
    _executeAction: function(action, record, context) {
        var self = this;
        
        // Handle our custom reload action
        if (action && action.type === 'ir.actions.client' && action.tag === 'reload') {
            // Show success notification if provided
            if (action.params && action.params.message) {
                this.displayNotification({
                    message: action.params.message,
                    type: action.params.type || 'success',
                    title: action.params.title || 'Success',
                    sticky: false
                });
            }
            
            // Close all modal dialogs
            $('.modal').modal('hide');
            
            // Force page reload after a short delay
            setTimeout(function() {
                window.location.reload(true);
            }, 500);
            
            return Promise.resolve();
        }
        
        // For other actions, proceed normally and then check if we need to refresh
        return this._super.apply(this, arguments).then(function(result) {
            // If this was a hold wizard action, set up refresh on close
            if (self.modelName === 'helpdesk.ticket.hold.wizard' || 
                self.modelName === 'helpdesk.hold.confirmation.wizard') {
                
                // Trigger close listener after action completes
                setTimeout(function() {
                    var $modal = self.$el ? self.$el.closest('.modal') : null;
                    if ($modal && $modal.length) {
                        $modal.trigger('hidden.bs.modal.hold_wizard');
                    }
                }, 100);
            }
            
            return result;
        });
    },
    
    /**
     * Debounced refresh function to avoid too frequent updates
     */
    _debouncedRefresh: function () {
        var self = this;
        clearTimeout(this._holdWizardRefreshTimeout);
        this._holdWizardRefreshTimeout = setTimeout(function() {
            self._softRefreshWizard();
        }, 1000);
    },
    
    /**
     * Soft refresh that updates data without disrupting user interaction
     */
    _softRefreshWizard: function () {
        if (this.renderer && this.renderer.state) {
            // Only refresh if not currently editing and not showing success
            if (!this.renderer.state.data.show_success_info) {
                this.reload({
                    keepChanges: true,
                    fieldNames: ['tagged_user_id', 'ticket_id', 'success_message', 'show_success_info']
                });
            }
        }
    },
    
    /**
     * Clean up intervals when view is destroyed
     */
    destroy: function() {
        if (this._holdWizardAutoRefreshInterval) {
            clearInterval(this._holdWizardAutoRefreshInterval);
        }
        if (this._holdWizardRefreshTimeout) {
            clearTimeout(this._holdWizardRefreshTimeout);
        }
        
        // Remove event listeners
        if (this.$el) {
            var $modal = this.$el.closest('.modal');
            if ($modal && $modal.length) {
                $modal.off('hidden.bs.modal.hold_wizard');
            }
        }
        
        this._super.apply(this, arguments);
    }
});

});