// TODO Determine this through authentication!
var userid = "testuser";


// variables to differentiate between single and dblclicks in the handleHighlight function
var DELAY = 250, clicks = 0, timer = null;

// websocket variable (initialized in $(document).ready
var socket



function getParameterByName(name) {
    name = name.replace(/[\[]/, "\\[").replace(/[\]]/, "\\]");
    var regex = new RegExp("[\\?&]" + name + "=([^&#]*)"),
        results = regex.exec(location.search);
    return results === null ? "" : decodeURIComponent(results[1].replace(/\+/g, " "));
}

function populateSaltsetIndicators() { 
    $("#saltsetA").html(getParameterByName("saltsetA"));
    $("#saltsetB").html(getParameterByName("saltsetB"));
}

function handleHighlights() {
    var mA = $('#modeSelector').val();
    // if we are in a mode that requires highlighting:
    if(mA !== "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch" && mA !== "http://127.0.0.1:8890/matchAlgorithm/disputedMatch") { 
        // indicate to user that they can click on scrollitems
        $('.scrollitem').css("cursor", "pointer"); 
        // handle the highlighting and display-selected logic:
        handleHighlight('left');
        handleHighlight('right');
    }
    else { 
        // indicate to user that they shouldn't bother clicking on stuff
        $('.scrollitem').css("cursor", "default");
    }
}

function handleHighlight(leftright) {
    // On a single click, we want to invoke the highlight logic
    // On a double click, we want to invoke the loadMatchesForSelected logic
    // i.e. we want to load only those labels (in the other list) that match the dblclicked label 
    // To differentiate between single and double click on the same element, we have to be slightly
    // hacky. See here: https://stackoverflow.com/questions/6330431/jquery-bind-double-click-and-single-click-separately
    $('#'+leftright+' .scrollitem').click(function() {
        var thisElement = $(this);
        clicks++; // count clicks
        if(clicks === 1) { 
            timer = setTimeout(function() {  
                // on single click: select (highlight) if previously unselected, or unselect if previously selected
                if(thisElement.hasClass(leftright+'Highlight')) { 
                    thisElement.removeClass(leftright+'Highlight');
                } else {
                    $('#'+leftright+' .scrollitem').removeClass(leftright+'Highlight');
                    thisElement.addClass(leftright+'Highlight');
                    // call server for context
                    var saltset = (leftright === "left") ? getParameterByName("saltsetA") : getParameterByName("saltsetB");
                    socket.emit('contextRequest', {saltset:saltset, uri:thisElement.attr('id'), leftright:leftright});
                }
                $('#'+leftright+'Selected').html('');
                $('#'+leftright+'Selected').html($('.'+leftright+'Highlight').html());
                handleScoreDisplay(); 
                clicks = 0; // reset counter
                // if both sides have a selection, always give option to confirm
                if($('#leftSelected').html() && $('#rightSelected').html()) { 
                    $('#confirmPanel').css('visibility', 'visible');
                }
                else { 
                    $('#confirmPanel').css('visibility', 'hidden');
                }
            }, DELAY);
        } else {
            // on double click: clear this list, retain the double clicked element,
            // and call loadMatchesForSelected to load up matches on the other list
            $('#'+leftright+' .scrollitem').removeClass(leftright+'Highlight');
            $('#'+leftright+' .scrollitem').css('display', 'none');
            thisElement.css('display', 'initial');

            // by double clicking, we are making this item a match reference
            // as such, we should style it differently;
            thisElement.addClass('matchReference');
            // remove the usual click handler; 
            thisElement.unbind('click');

            clearTimeout(timer); // prevent single-click action

            // ...and give it a different click behaviour (dbl-click to exit match
            // reference mode, i.e. return to full lists on both sides)
            thisElement.click(function() { refreshLists() });
            clicks = 0; // reset counter
            loadMatchesForSelected(leftright, thisElement);
        }

    });

    $('#'+leftright+' .scrollitem').dblclick(function(e) { 
        e.preventDefault(); // cancel system double-click event in favour of above hack!
    });

    $('#'+leftright+' .scrollitem').mousedown(function(e) { 
        e.preventDefault(); // prevent spurious word selection through double-click
    });
}

function handleConfirmDispute() { 
    $('#confirmPanel i').click(function() { 
        var confStatus;
        var confMsg
        if ($(this).hasClass("fa-thumbs-up")) {
            confStatus = "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch";
            confMsg = "Confirm match: ";

        }
        else { 
            confStatus = "http://127.0.0.1:8890/matchAlgorithm/disputedMatch";
            confMsg = "Dispute match: ";
        }


    var confReason = prompt(confMsg + $('#leftSelected').html() + " :: " + $('#rightSelected').html() + "\nPlease enter a reason below.");
    if(confReason != null) { 
        // generate the aligned uri (based on left uri + right uri)
        var lefturi = $('.leftHighlight').attr("id");
        var righturi = $('.rightHighlight').attr("id");
        var aligneduri = "http://127.0.0.1:8890/matchDecisions/" + lefturi.replace("http://", "").replace(/\//g, "__") + "___" + righturi.replace("http://", "").replace(/\//g, "__");
        // remember this decision locally
        var thisMatch = {
            matchuri: aligneduri, 
            lefturi: lefturi, 
            righturi:righturi, 
            leftlabel:$('#leftSelected').html(), 
            rightlabel:$('#rightSelected').html(), 
            reason:confReason
        };
        if(fuzz[confStatus] !== undefined) { 
            fuzz[confStatus].push(thisMatch);
        } else { 
            fuzz[confStatus] = [thisMatch];
        }
        // and send this decision to the server, for persistent storage
        socket.emit('confirmDisputeEvent', {confStatus: confStatus, lefturi: lefturi, righturi: righturi, aligneduri: aligneduri, confReason: confReason, timestamp: Date.now(), user:userid});
    }

    });
}
function handleScoreDisplay() { 
    $('#selectedScore').html('');
    // now grab the left and right selected
    var leftSel = $('#leftSelected').html();
    var rightSel = $('#rightSelected').html();
    if(leftSel && rightSel) { 
        // both sides have a selection
        // see if we have it in our bag
        var mA = $("#modeSelector").val();
        for(var match in fuzz[mA])  {
            if(fuzz[mA][match]["leftlabel"] === leftSel && 
                    fuzz[mA][match]["rightlabel"] === rightSel) { 
                        console.log(mA)
                            if(mA === "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch" || mA === "http://127.0.0.1:8890/matchAlgorithm/disputedMatch") { 
                                $('#selectedScore').html(fuzz[mA][match]["reason"])
                            } else { 
                                $('#selectedScore').html(fuzz[mA][match]["score"]);
                            }
                        break;
                    }
        }
    }
}


function handleLocks() { 
    $('.lock').toggleClass('lockActive');
    $('#scores').toggleClass('hiddenScores');
    if ($('#lockcentre').hasClass("lockActive")) {
        $('#lockcentre').html('<i class="fa fa-lock fa-2x"></i>')
    } else {
        $('#lockcentre').html('<i class="fa fa-unlock-alt fa-2x"></i>')
    }
}

function handleScrolling() { 
    $('.scrollable').on('scroll', function() { 
        if($('#lockcentre').hasClass("lockActive")) {
            //need to synchronize scrolling across both lists
            var top = $(this).scrollTop();
            $('.scrollable').scrollTop(top);
        }
    });
}

function scrollLock(leftright) {
    // set the scroll location of leftright to that of the reference (i.e. the other one)
    var reference = (leftright === "left") ? "right" : "left";
    $('#' + leftright).scrollTop($('#' + reference).scrollTop());
}

function refreshLists() {
    // 0. Get rid of any previous selections...
    $('#leftSelected').html('');
    $('#rightSelected').html('');
    $('#selectedScore').html('');
    $('#confirmPanel').css("visibility", "hidden");
    // ... and adjust style depending on mode.
    modalAdjust();
    // 1. Get the match algorithm (mode) from the selection list
    var mA = $("#modeSelector").val();
    var mode = "match";
    if(mA === "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch" || mA === "http://127.0.0.1:8890/matchAlgorithm/disputedMatch") {
        mode = "displayDecisions";
    }
    // 2. Grab the lists (so we don't have to keep searching the DOM every time):
    var leftList = $("#left");
    var rightList = $("#right");
    var scores = $("#scores");
    // 3. Clear the lists:
    leftList.html("");
    rightList.html("");
    scores.html("");
    // 2. Loop through the relevant part of the fuzz object
    var newLeftHTML = "";
    var newRightHTML = "";
    var newScoresHTML = "";
    var alternate = 1; // used for alternating stripe effect in display decisions view
    var altString;
    for (var match in fuzz[mA]) { 
        alternate *= -1;
        if(alternate>0 && mode === "displayDecisions") { 
            altString = " alternate";
        } else {
            altString = "";
        }
        // 3. Populate the left and right list with the IDs and names from the fuzz object
        if(typeof fuzz[mA][match]["lefturi"] !== 'undefined') { 
            newLeftHTML += '<div class="scrollitem'+altString+'" id="' + fuzz[mA][match]["lefturi"] + 
                '" title="' + fuzz[mA][match]["lefturi"] + '">' + fuzz[mA][match]["leftlabel"] + '</div>\n';
        }
        if(typeof fuzz[mA][match]["righturi"] !== 'undefined') { 
            newRightHTML += '<div class="scrollitem'+altString+'"+ id="' + fuzz[mA][match]["righturi"] + 
                '" title="' + fuzz[mA][match]["righturi"] + '">' + fuzz[mA][match]["rightlabel"] + '</div>\n';
        }
        if(mode === "displayDecisions") {
            newScoresHTML += '<div class="scrollitem'+altString+'" title="'+ fuzz[mA][match]["reason"] + '">' + fuzz[mA][match]["reason"] + '&nbsp;</div>\n';
        } else {
            newScoresHTML += '<div class="scrollitem">' + fuzz[mA][match]["score"] + '</div>\n';
        }
    }
    leftList.html(newLeftHTML);
    rightList.html(newRightHTML);
    scores.html(newScoresHTML);
    handleHighlights();
}

function loadMatchesForSelected(leftright, selected) { 
    var target = (leftright === "left") ? "right" : "left";
    // user has double clicked on a name (on the left or right)
    // populate the left/rightSelected div appropriately
    $('#' + leftright +'Selected').html(selected.html())
        $('#' + target + 'Selected').html("")
        $('#selectedScore').html("")
        // load up all matches to that name on the other list
        var mA = $("#modeSelector").val();
    var sourceList = $("#" + leftright);
    var targetList = $("#" + target);
    var scoresList = $("#scores");
    // clear target list
    targetList.html("");
    var newTargetHTML = "";
    var newScoresHTML = "";
    for (var match in fuzz[mA]) { 
        // re-populate target list with items matching dblclicked name 
        if(fuzz[mA][match][leftright+"label"] === selected.html()) {
            newTargetHTML += '<div class="scrollitem" id="' + fuzz[mA][match][target+"uri"] + 
                '">' + fuzz[mA][match][target+"label"] + '</div>\n';
            newScoresHTML += '<div class="scrollitem">' + fuzz[mA][match]["score"] + '</div>\n';
        }
    }
    scoresList.html(newScoresHTML);
    targetList.html(newTargetHTML);

    // since we cleared all the scrollitems in the target list before loading matches,
    // need to reinitialize highlighting (i.e. click handlers) there
    handleHighlight(target); 

}

function modalAdjust() {  
    // Adjust width of score/reason column, and decide whether lock controls / confirmation panel should be visible, depending on mode
    // (matching mode, or review mode, i.e. view confirmations / disputations)
    var mA = $('#modeSelector').val();
    if(mA === "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch" || mA === "http://127.0.0.1:8890/matchAlgorithm/disputedMatch") {  
        $('#scores').css("width", "370px");
        $('#scores').css("display", "block");
        $('.lockcontrols').css('visibility', 'hidden');
        $('#confirmPanel').css('visibility', 'hidden');
        // always lock scrolling in display-decisions mode
        if(!($('#lockcentre').hasClass('lockActive'))) { 
            handleLocks();
        }
    }
    else if (mA === "http://127.0.0.1:8890/matchAlgorithm/simpleList") { 
        // no scores to display on an unmatched simple listing...
        $('#scores').css("display", "none");
        // since the lists aren't matched, locked scrolling makes no sense in this mode
        $('.lockcontrols').css('visibility', 'hidden');
        if($('#lockcentre').hasClass('lockActive')) { 
            handleLocks();
        }
    }
    else { 
        $('#scores').css("width", "50px");
        $('#scores').css("display", "block");
        $('.lockcontrols').css('visibility', 'visible');
        // don't reveal confirm panel since it should only show after user selects an item on each side
    }

}

$(document).ready(function() { 
    // initialize stuff
    populateSaltsetIndicators(); handleLocks(); handleScrolling(); refreshLists(); handleConfirmDispute(); 

    // set up websocket
    socket=io.connect('http://' + document.domain + ':' + location.port); 
    socket.on('connect', function() { 
        socket.emit('clientConnectionEvent', 'Client connected.');
        console.log("Connected to server");
    });

// set up websocket handlers
socket.on('confirmDisputeHandled', function(msg) {

})

socket.on('contextRequestHandled', function(msg) { 
    console.log("Context request handled: ", msg);
    var contextElement = $("#" + msg["leftright"]  + "Context");
    var newContextHTML = ""
    // create divs for each type of variable
    for (var i = 0; i < msg["results"]["variables"].length; i++) { 
        newContextHTML += '<div class="contextVar" id="' + msg["results"]["variables"][i] + '">' + '</div>\n';
    }
console.log("Attempting to set context element html to " + newContextHTML);
contextElement.html(newContextHTML);
console.log(contextElement)
    // populate the divs
    for (var i = 0; i < msg["results"]["bindings"].length; i++) { 
        console.log("i: " + i);
        for (var j = 0; j < msg["results"]["variables"].length; j++) { 
            var varName =  msg["results"]["variables"][j];
            console.log("Using " + varName);
            console.log("Object: " +$(".contextVar." + varName));
            var prevContent = $("#" + msg["leftright"] + "Context .contextVar#" + varName).html();
            var newContent = '<div class="contextItem">' + msg["results"]["bindings"][i][varName]["value"] + "</div>";
            $("#" + msg["leftright"] + "Context  .contextVar#" + varName).html(prevContent + newContent);

        }
    }
})
});
