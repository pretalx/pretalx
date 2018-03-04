$(function () {
    "use strict";

    $(".datetimepickerfield").each(function () {
        $(this).datetimepicker({
            format: $("body").attr("data-datetimeformat"),
            locale: $("body").attr("data-datetimelocale"),
            useCurrent: false,
            showClear: !$(this).prop("required"),
            icons: {
                time: 'fa fa-clock-o',
                date: 'fa fa-calendar',
                up: 'fa fa-chevron-up',
                down: 'fa fa-chevron-down',
                previous: 'fa fa-chevron-left',
                next: 'fa fa-chevron-right',
                today: 'fa fa-screenshot',
                clear: 'fa fa-trash',
                close: 'fa fa-remove'
            }
        });
    });

    $(".datepickerfield").each(function () {
        var opts = {
            format: $("body").attr("data-dateformat"),
            locale: $("body").attr("data-datetimelocale"),
            useCurrent: false,
            showClear: !$(this).prop("required"),
            icons: {
                time: 'fa fa-clock-o',
                date: 'fa fa-calendar',
                up: 'fa fa-chevron-up',
                down: 'fa fa-chevron-down',
                previous: 'fa fa-chevron-left',
                next: 'fa fa-chevron-right',
                today: 'fa fa-screenshot',
                clear: 'fa fa-trash',
                close: 'fa fa-remove'
            }
        };
        $(this).datetimepicker(opts);
    });
    function luminanace(r, g, b) {
        var a = [r, g, b].map(function (v) {
            v /= 255;
            return v <= 0.03928
                ? v / 12.92
                : Math.pow( (v + 0.055) / 1.055, 2.4 );
        });
        return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
    }
    Math.round = (function(){
        var round = Math.round;

        return function (number, decimals) {
            decimals = +decimals || 0;

            var multiplier = Math.pow(10, decimals);

            return round(number * multiplier) / multiplier;
        };
    })();
    function contrast(rgb1, rgb2) {
        var l1 = luminanace(rgb1[0], rgb1[1], rgb1[2]) + 0.05,
             l2 = luminanace(rgb2[0], rgb2[1], rgb2[2]) + 0.05,
             ratio = l1/l2
        if (l2 > l1) {ratio = 1/ratio}
        return ratio.toFixed(1)
    }
    $("input#id_primary_color")
        .colorpicker({
            format: 'hex',
            align: 'left',
            customClass: 'colorpicker-2x',
            sliders: {
                saturation: {
                  maxLeft: 200,
                  maxTop: 200
                },
                hue: {
                  maxTop: 200
                },
                alpha: {
                  maxTop: 200
                }
            },
        })
        .on('change', function (e) {
            var output = e.colorpicker.picker.find('.colorpicker-color div')
            var rgb = e.color.toRgb()
            var c = contrast([255,255,255], [rgb.r, rgb.g, rgb.b])
            var mark = 'times'
            if (c > 4.5) { mark = 'check-circle-o' }
            if (c > 7) { mark = 'check-circle' }
            output.html('contrast: ' + c + ' <span class="fa fa-' + mark + '"></span>')
            $(output).css('color', e.color.toString())
        }
    );

    $(".datetimepicker[data-date-after], .datepickerfield[data-date-after]").each(function() {
        var later_field = $(this),
            earlier_field = $($(this).attr("data-date-after")),
            update = function () {
                var earlier = earlier_field.data('DateTimePicker').date(),
                    later = later_field.data('DateTimePicker').date();
                if (earlier === null) {
                    earlier = false;
                } else if (later !== null && later.isBefore(earlier) && !later.isSame(earlier)) {
                    later_field.data('DateTimePicker').date(earlier.add(1, 'h'));
                }
                later_field.data('DateTimePicker').minDate(earlier);
            };
        update();
        earlier_field.on("dp.change", update);
    });
    if ($("#answer-options").length) {

        $("#id_variant").change(question_page_toggle_view);
        $("#id_required").change(question_page_toggle_view);
        question_page_toggle_view();
    }
});

function question_page_toggle_view() {
    var show = $("#id_variant").val() == "choices" || $("#id_variant").val() == "multiple_choice";
    $("#answer-options").toggle(show);

    show = $("#id_variant").val() == "boolean" && $("#id_required").prop("checked");
    $(".alert-required-boolean").toggle(show);
}
