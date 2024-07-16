odoo.define('sh_backmate_theme_adv.ListController', function (require) {
    "use strict";

    var ListController = require('web.ListController');

    ListController.include({
        events: _.extend({}, ListController.prototype.events, {
            'click .sh_refresh': '_onClickRefreshView',
        }),
        _onClickRefreshView:function (ev) {
           console.log("Refresh")
           this.reload()
        }
    });

    var ListRenderer = require('web.ListRenderer');

	ListRenderer.include({
		async _renderView() {
			// Fix issue of sticky three dots
			var self = this;
			return this._super.apply(this, arguments).then(function () {
				self.$el.find('thead').append(
								$('<i class="o_optional_columns_dropdown_toggle fa fa-ellipsis-v"/>')
							);
			});


		}
		    
	});

    
});
odoo.define('sh_backmate_theme_adv.BasicController', function (require) {
    "use strict";

    var BasicController = require('web.BasicController');

    BasicController.include({
        events: _.extend({}, BasicController.prototype.events, {
            'click .sh_refresh': '_onClickRefreshView',
        }),
        _onClickRefreshView:function (ev) {
           console.log("Refresh")
           this.reload()
        }
    });
});