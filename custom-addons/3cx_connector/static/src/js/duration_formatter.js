odoo.define('3cx_connector.DurationFormatter', function (require) {
    "use strict";

    const fieldRegistry = require('web.field_registry');
    const FieldChar = require('web.basic_fields').FieldChar;

    const DurationFormatter = FieldChar.extend({
        _renderReadonly: function() {
            const duration = parseInt(this.value) || 0;
            const minutes = Math.floor(duration / 60);
            const seconds = duration % 60;
            this.$el.text(`${minutes}:${seconds.toString().padStart(2, '0')}`);
        }
    });

    fieldRegistry.add('duration_formatter', DurationFormatter);
    return DurationFormatter;
});