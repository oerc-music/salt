// TODO Determine this through authentication!
var userid = "testuser";


// variables to differentiate between single and dblclicks in the handleHighlight function
var DELAY = 250, clicks = 0, timer = null;

// websocket variable (initialized in $(document).ready
var socket

function handleHighlights() {
    // handle the highlighting and display selected logic:
    handleHighlight('left');
    handleHighlight('right');
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

function handleConfirmDisconfirm() { 
    $('#confirmPanel i').click(function() { 
            var confStatus;
            var confMsg
            if ($(this).hasClass("fa-thumbs-up")) {
                confStatus = "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch";
                confMsg = "Confirm match: ";

            }
            else { 
                confStatus = "http://127.0.0.1:8890/matchAlgorithm/disconfirmedMatch";
                confMsg = "Disconfirm match: ";
            }


            var confReason = prompt(confMsg + $('#leftSelected').html() + " :: " + $('#rightSelected').html() + "\nPlease enter a reason below.");
            if(confReason != null) { 
                // generate the aligned uri (based on left uri + right uri)
                var lefturi = $('.leftHighlight').attr("id");
                var righturi = $('.rightHighlight').attr("id");
                var aligneduri = "http://127.0.0.1:8890/matchDecisions/" + lefturi.replace("http://", "").replace(/\//g, "__") + "___" + righturi.replace("http://", "").replace(/\//g, "__");
                // remember this decision locally
                fuzz[confStatus].push(
                        {
                            matchuri: aligneduri, 
                            lefturi: lefturi, 
                            righturi:righturi, 
                            leftlabel:$('#leftSelected').html(), 
                            rightlabel:$('#rightSelected').html(), 
                            reason:confReason
                        });
                // and send this decision to the server, for persistent storage
                socket.emit('confirmDisconfirmEvent', {confStatus: confStatus, lefturi: lefturi, righturi: righturi, aligneduri: aligneduri, confReason: confReason, timestamp: Date.now(), user:userid});
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
               if(mA === "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch" || mA === "http://127.0.0.1:8890/matchAlgorithm/disconfirmedMatch") { 
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
    // 1. Get the match algorithm from the selection list
    var mA = $("#modeSelector").val();
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
    for (var match in fuzz[mA]) { 
        // 3. Populate the left and right list with the IDs and names from the fuzz object
        newLeftHTML += '<div class="scrollitem" id="' + fuzz[mA][match]["lefturi"] + 
                        '">' + fuzz[mA][match]["leftlabel"] + '</div>\n';
        newRightHTML += '<div class="scrollitem" id="' + fuzz[mA][match]["righturi"] + 
                        '">' + fuzz[mA][match]["rightlabel"] + '</div>\n';
        newScoresHTML += '<div class="scrollitem">' + fuzz[mA][match]["score"] + '</div>\n';
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

$(document).ready(function() { 
    // initialize stuff
    handleLocks(); handleScrolling(); refreshLists(); handleConfirmDisconfirm(); 

    // set up websocket
   socket=io.connect('http://' + document.domain + ':' + location.port); 
   socket.on('connect', function() { 
       socket.emit('clientConnectionEvent', 'Client connected.');
   });

    // set up websocket handlers
   socket.on('confirmDisconfirmHandled', function(msg) {
       console.log("Server handled: ", msg)
   })
});
