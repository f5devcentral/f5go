/**
 * Created by Sean Smith on 10/11/16.
 */

document.getElementById('delete').onclick = function () {
    var lists = document.getElementsByName('lists');
    var message = 'Doing this will delete the link from ';
    if (lists.length == 1) {
        message += 'the \'' + lists[0].value + '\' keyword';
    }
    else if (lists.length == 2) {
        message += 'the following keywords: \'' + lists[0].value + '\' and \'' + lists[1].value + '\'';
    } else {
        message += 'the following keywords: ';
        for (var i = 0; i < lists.length; i++) {
            if (i + 1 != lists.length) {
                message += '\'' + lists[i].value + '\', ';
            }
            else {
                message += 'and \'' + lists[i].value + '\'';
            }
        }
    }
    if (lists.length > 1) {
        message += '\n\nIf you just want to disassociate it from a keyword uncheck it and submit';
    }
    return confirm(message);
};