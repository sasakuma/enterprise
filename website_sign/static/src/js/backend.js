
openerp.website_sign = function(instance, local) {
    'use strict';

    var IFrameWidget = openerp.Widget.extend({ // FIXME ugly
        tagName: 'iframe',
        init: function(parent, url) {
            this._super(parent);
            this.url = url;
        },
        start: function() {
            this.$el.css({height: '100%', width: '100%', border: 0});
            this.$el.attr({src: this.url});
            this.$el.on("load", this.bind_events.bind(this));
            return this._super();
        },
        bind_events: function(){
            this.$el.contents().click(this.iframe_clicked.bind(this));
        },
        iframe_clicked: function(e){
        }
    });

    local.SignIFrameWidget = IFrameWidget.extend({
        init: function(parent, options, cp_content) {
            if(!options.context.src) { // FIXME ugly
                window.location.href = '/web';
            }
            this._super(parent, options.context.src || '');
            this.cp_content = cp_content || {};
        },

        start: function() {
            var self = this;
            this.$el.addClass('o_sign_iframe');
            return self._super().then(function() {
                self.actionManager = self.getParent();
            });
        },

        bind_events: function() {
            this._super();

            if(this.el.contentDocument.location.href.slice(-this.url.length) !== this.url) {
                var action = this.getOnLeaveAction(this.el.contentDocument.location.href);
                var options = this.getOnLeaveOptions(this.el.contentDocument.location.href);
                if(action && !$.isEmptyObject(action)) {
                    this.do_action(action, options);
                    return false;
                }
            }
            
            var $mainContent = this.$el.contents().find('body main').detach();
            if($mainContent.length > 0)
                $mainContent.appendTo(this.$el.contents().find('body').html(''));
        },

        getOnLeaveAction: function(newURL) {
            return {};
        },

        getOnLeaveOptions: function(newURL) {
            return {
                additional_context: {src: newURL}
            };
        },

        do_show: function() {
            this._super();
            this.$el.attr('src', this.url);
        },
    });

    local.DashboardIframe = local.SignIFrameWidget.extend({
        init: function(parent) {
            var $toggleGroup = $('<div/>').addClass("btn-group btn-group-sm");

            var $toggleDropdown = $('<button/>', {'data-toggle': 'dropdown', 'type': 'button'}).addClass("btn btn-default dropdown-toggle");
            this.$dropdown = $('<ul/>', {'role': 'menu'}).addClass("dropdown-menu filters-menu");

            $toggleGroup.append($toggleDropdown);
            $toggleGroup.append(this.$dropdown);

            $toggleDropdown.html('<span class="fa fa-filter"/> Filters <span class="caret"></span>');
            this.$dropdown.append($('<li/>').append($('<a/>', {html: "Favorites Only"})).data({'eventSelector': "#o_sign_show_favorites_toggle", 'hideSelector': "label[for='o_sign_show_favorites_toggle']"}));
            this.$dropdown.append($('<li/>').addClass("divider"));
            this.$dropdown.append($('<li/>').append($('<a/>', {html: "Show Archives"})).data({'eventSelector': "#o_sign_show_archives_toggle", 'hideSelector': "label[for='o_sign_show_archives_toggle']"}));

            this._super(parent, {context: {src: '/sign'}}, {$searchview_buttons: $toggleGroup});
        },

        getOnLeaveAction: function(newURL) {
            return {
                type: "ir.actions.client",
                tag: 'website_sign.dashboard_item_template',
                name: "New Template"
            };
        },

        iframe_clicked: function(e) {
            if(e.button !== 0)
                return true;

            var $elem = $(e.target).closest('.o_sign_dashboard_item > a');
            if($elem.length > 0 && $elem.attr('href')) {
                e.preventDefault();

                this.do_action({
                    type: "ir.actions.client",
                    tag: 'website_sign.dashboard_item' + (($elem.attr('href').indexOf('template') >= 0)? '_template' : '_document'),
                    name: (($elem.attr('href').indexOf('template') >= 0)? "Template \"" : "Document \"") + $elem.find('.o_sign_dashboard_item_title').text() + "\"",
                    context: {
                        src: $elem.attr('href')
                    }
                });
            }
        }
    });

    local.TemplateIframe = local.SignIFrameWidget.extend({
        init: function(parent, options) {
            var sendButton = $('<button/>', {html: "Send"}).addClass('btn btn-primary btn-sm').data('eventSelector', '.o_sign_send_template_button');
            var shareButton = $('<button/>', {html: "Share"}).addClass('btn btn-link btn-sm').data('eventSelector', '.o_sign_share_template_button');

            this._super(parent, options, {
                $buttons: sendButton.add(shareButton)
            });
        },

        getOnLeaveAction: function(newURL) {
            if(newURL.indexOf('document') >= 0) {
                return {
                    type: "ir.actions.client",
                    tag: 'website_sign.dashboard_item_document',
                    name: "New Document"
                };
            }
            else {
                return {
                    type: "ir.actions.client",
                    tag: 'website_sign.dashboard_item_template',
                    name: "New Template"
                };
            }
        },
    });

    local.DocumentIframe = local.SignIFrameWidget.extend({
        init: function(parent, options) {
            var cancelButton = $('<button/>', {html: "Cancel Request"}).addClass('btn btn-default btn-sm').data('eventSelector', '.o_sign_cancel_request_button');

            this._super(parent, options, {
                $buttons: cancelButton
            });
        },

        getOnLeaveAction: function(newURL) {
            if(newURL.indexOf('document') >= 0)
                return {};
            else {
                return {
                    type: "ir.actions.client",
                    tag: 'website_sign.dashboard',
                    name: 'Digital Signatures Documents'
                };
            }
        },

        getOnLeaveOptions: function(newURL) {
            return $.extend(this._super(newURL), {clear_breadcrumbs: true});
        },
    });

    instance.web.client_actions.add('website_sign.dashboard', 'instance.website_sign.DashboardIframe');

    instance.web.client_actions.add('website_sign.dashboard_item_template', 'instance.website_sign.TemplateIframe');
    instance.web.client_actions.add('website_sign.dashboard_item_document', 'instance.website_sign.DocumentIframe');
};