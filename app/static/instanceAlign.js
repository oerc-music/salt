// TODO Determine this through authentication!
var userid = "testuser";


// variables to differentiate between single and dblclicks in the handleHighlight function
var DELAY = 250, clicks = 0, timer = null;

// websocket variable (initialized in $(document).ready
var socket;



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
    $('#'+leftright+' .scrollitem').click(function(e) {
        if($(e.target).is("i") || 
            $(e.target).hasClass("unlisted") || 
            $(e.target).parent().hasClass("unlisted") ){ 
            // if this click event is bubbling up from a click on the eye icon (i.e. the user
            // wanted to toggle listing/unlisting, not highlighting);
            // or, if the clicked scrollitem is currently unlisted;
            // of, if the click was on the internal span of such a scroll item;
            // do not handle highlighting actions for this event
            return;
        }
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
                    socket.emit('contextRequest', {saltset:saltset, uri:thisElement.attr('title'), leftright:leftright});
                }
                $('#'+leftright+'Selected').html('');
                $('#'+leftright+'Selected').html($('.'+leftright+'Highlight span').html());
                handleScoreDisplay(); 
                clicks = 0; // reset counter
                // if both sides have a selection, give option to confirm/dispute
                if($('#leftSelected').html() && $('#rightSelected').html()) { 
                    $('#singleConfirmDispute').css('display', 'inline');
                    $('#bulkConfirm').css('display', 'none');
                } else { 
                    $('#singleConfirmDispute').css('display', 'none');
                    // if only one side has a selection, give option to bulk confirm
                    if($('#leftSelected').html() || $('#rightSelected').html()) { 
                        $('#bulkConfirm').css('display', 'inline');
                    } else { 
                        $('#bulkConfirm').css('display', 'none');
                    }
                }
            }, DELAY);
        } else {
            // on double click: clear this list, retain the double clicked element,
            // and call loadMatchesForSelected to load up matches on the other list
            // .. but only if we are in a matching mode (i.e. anything but simplelist)
            if($("#modeSelector").val() !== "http://127.0.0.1:8890/matchAlgorithm/simpleList") { 
                $('#'+leftright+' .scrollitem').removeClass(leftright+'Highlight');
                $('#'+leftright+' .scrollitem').css('display', 'none');
                thisElement.css('display', 'initial');
                // by double clicking, we are making this item a match reference
                // as such, we should style it differently;
                thisElement.addClass('matchReference');
                // ...and give it a different click behaviour (dbl-click to exit match
                // reference mode, i.e. return to full lists on both sides)
                thisElement.click(function() { clicks = 0; refreshLists();  });
                loadMatchesForSelected(leftright, thisElement.find("span"));
            }
            clearTimeout(timer); // prevent single-click action
            clicks = 0; // reset counter
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

    $('#bulkConfirm').click(function() {
        // identify the URI and saltset on which this bulk-confirm is anchored
        // i.e. the selected item that is being matched to all listed items in the other set
        var anchoruri;
        var target;
        var leftright;
        var confStatus = "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch";
        // user only sees this button if exactly one side has a selection
        if($('#leftSelected').html()) { 
            anchoruri = $('.leftHighlight').attr("title");
            leftright = "left";
            target = "right";
        } else { 
            anchoruri = $('.rightHighlight').attr("title");
            leftright = "right";
            target = "left";
        }
            
        var confMsg = "Bulk-Confirming match between " + $('#'+leftright+'Selected').html() + 
                      " in the " + leftright + "-hand list and " + $("#" + target + " .scrollitem").not(".unlisted").length
                      + " active items in the " + target + "-hand list. If you are sure, "+
                      "please enter a reason below.";
        var confReason = prompt(confMsg);
        if(confReason != null) { 
            // generate matches between the anchor item and each target item
            var bulkMatches = $.map($("#"+target+" .scrollitem").not(".unlisted"), 
                    function(targetItem) {
                        var targeturi = $(targetItem).attr("title") ;
                        var aligneduri = "http://127.0.0.1:8890/matchDecisions/" + anchoruri.replace("http://", "").replace(/\//g, "__") + "___" + targeturi.replace("http://", "").replace(/\//g, "__");
                        // set up this match. Why use the longwinded syntax instead of nice JSON? 
                        // Because JavaScript. See http://www.unethicalblogger.com/2008/03/21/javascript-wonks-missing-after-property-id.html
                        var thisMatch = {};
                        thisMatch["aligneduri"] =  aligneduri;
                        thisMatch[leftright+"uri"] = anchoruri; 
                        thisMatch[target+"uri"] = targeturi; 
                        thisMatch[leftright+"label"] = $('#' + leftright + 'Selected').html(); 
                        thisMatch[target+"label"] = $(targetItem).find('span').html(); 
                        thisMatch["confReason"] = confReason;
                        
                        // remember each match locally
                        localStoreConfirmDispute(thisMatch, confStatus);
                        return thisMatch;
                    });
            socket.emit('bulkConfirmEvent', {matches: bulkMatches, confStatus: confStatus, confReason: confReason, timestamp: Date.now(), user:userid});
        }
    });

    $('#singleConfirmDispute i').click(function(e) { 
        var confStatus;
        var confMsg;
        var confReason = prompt($('#leftSelected').html() + " :: " + $('#rightSelected').html() + "\nPlease enter a reason below.");
        var element = e.target;
        if(confReason != null) { 
            // indicate that we're talking to the server and waiting for a response
            if ($(element).hasClass("fa-thumbs-up")) {
                confStatus = "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch";
                confMsg = "Confirm match: ";
                $(element).removeClass("fa-thumbs-up").addClass("fa-cog fa-spin");

            } else { 
                confStatus = "http://127.0.0.1:8890/matchAlgorithm/disputedMatch";
                confMsg = "Dispute match: ";
                $(element).removeClass("fa-thumbs-down").addClass("fa-cog fa-spin");
            }// generate the aligned uri (based on left uri + right uri)

            var lefturi = $('.leftHighlight').attr("title");
            var righturi = $('.rightHighlight').attr("title");
            var aligneduri = "http://127.0.0.1:8890/matchDecisions/" + lefturi.replace("http://", "").replace(/\//g, "__") + "___" + righturi.replace("http://", "").replace(/\//g, "__");
            
            // remember this decision locally
            var thisMatch = {
                matchuri: aligneduri, 
                lefturi: lefturi, 
                righturi:righturi, 
                leftlabel:$('#leftSelected').html(), 
                rightlabel:$('#rightSelected').html(), 
                confReason:confReason
            };
            console.log("Reason was " + thisMatch["confReason"]);
            localStoreConfirmDispute(thisMatch, confStatus);

            // and send this decision to the server, for persistent storage
            socket.emit('confirmDisputeEvent', {confStatus: confStatus, lefturi: lefturi, righturi: righturi, aligneduri: aligneduri, confReason: confReason, timestamp: Date.now(), user:userid});
        }
    });
}

function localStoreConfirmDispute(match, confStatus) {
    console.log("Locally storing " + match["aligneduri"]);
    if(fuzz[confStatus] !== undefined) { 
        fuzz[confStatus].push(match);
    } else { 
        fuzz[confStatus] = [match];
    }
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
                        if(mA === "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch" || mA === "http://127.0.0.1:8890/matchAlgorithm/disputedMatch") { 
                            $('#selectedScore').html(fuzz[mA][match]["confReason"])
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
    // Store the search string as a regex if it exists
    var searchString = $("#searchbox").val();
    var searchRE;
    if(searchString !== "") {
        searchRE = new RegExp(searchString);
        // show waiting icon to indicate that the search is in progress:
        $("#search i").removeClass("fa-search").addClass("fa-cog fa-spin");
    }
    var searchMode = $('#search input[type="radio"]:checked').val();
    // Get rid of any previous selections...
    $('#leftSelected').html('');
    $('#rightSelected').html('');
    $('#selectedScore').html('');
    $('#singleConfirmDispute').css("display", "none");
    // ... and adjust style depending on mode.
    modalAdjust();
    // Get the match algorithm (mode) from the selection list
    var mA = $("#modeSelector").val();
    var mode;
    if(mA === "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch" || mA === "http://127.0.0.1:8890/matchAlgorithm/disputedMatch") {
        mode = "displayDecisions";
    }
    else if (mA == "http://127.0.0.1:8890/matchAlgorithm/simpleList") { 
        mode = "simpleList";
    }
    else { 
        mode = "match";
    }
    // Grab the lists (so we don't have to keep searching the DOM every time):
    var leftList = $("#left");
    var rightList = $("#right");
    var scores = $("#scores");
    // Clear the lists:
    leftList.html("");
    rightList.html("");
    scores.html("");
    // Loop through the relevant part of the fuzz object
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
        // Populate the left and right list with URIs and labels from the fuzz object
        // Only include if no search is specified, or the search is being performed on
        // the other side (leftright), or the regex matches
        if(typeof fuzz[mA][match]["lefturi"] !== 'undefined') {
            if(typeof(searchRE) === "undefined" || searchMode === "Right" || searchRE.test(fuzz[mA][match]["leftlabel"])) { 
                newLeftHTML += '<div class="scrollitem'+ altString + 
                    '" title="' + fuzz[mA][match]["lefturi"] + '"><span>' + fuzz[mA][match]["leftlabel"] + '</span> <i class="fa fa-eye-slash" onclick="toggleListExclusion(this)"></i></div>\n';
            } else if(mode !== "simpleList") { 
                // if we are in any mode where left matches right (i.e. anything but simpleList)...
                // ...continue on to next match set and print nothing on either side for this one
                continue;
            }
        }
        if(typeof fuzz[mA][match]["righturi"] !== 'undefined') { 
            if(typeof(searchRE) === "undefined" || searchMode === "Left" || searchRE.test(fuzz[mA][match]["rightlabel"])) { 
                newRightHTML += '<div class="scrollitem' + altString +
                    '" title="' + fuzz[mA][match]["righturi"] + '"><span>' + fuzz[mA][match]["rightlabel"] + '</span> <i class="fa fa-eye-slash" onclick="toggleListExclusion(this)"></i></div>\n';
            } else if (mode !== "simpleList") { 
                // see above (for left label)
               continue;
            }
        }   
        if(mode === "displayDecisions") {
            newScoresHTML += '<div class="scrollitem'+altString+'" title="'+ fuzz[mA][match]["confReason"] + '">' + fuzz[mA][match]["confReason"] + '&nbsp;</div>\n';
        } else {
            newScoresHTML += '<div class="scrollitem">' + fuzz[mA][match]["score"] + '</div>\n';
        }
    }
    leftList.html(newLeftHTML);
    rightList.html(newRightHTML);
    scores.html(newScoresHTML);
    handleHighlights();
    if(searchString !== "") {
        // we're done; change icon back from "waiting" to "search"
        $("#search i").removeClass("fa-cog fa-spin").addClass("fa-search");
    }
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
            newTargetHTML += '<div class="scrollitem" title="' + fuzz[mA][match][target+"uri"] + 
                '"><span>' + fuzz[mA][match][target+"label"] + '</span> <i class="fa fa-eye-slash" onclick="toggleListExclusion(this)"></i></div>\n';
            newScoresHTML += '<div class="scrollitem">' + fuzz[mA][match]["score"] + '</div>\n';
        }
    }
    scoresList.html(newScoresHTML);
    targetList.html(newTargetHTML);

    // since we cleared all the scrollitems in the target list before loading matches,
    // need to reinitialize highlighting (i.e. click handlers) there
    handleHighlight(target); 

}

function toggleListExclusion(element) { 
    if($(element).hasClass("fa-eye-slash")) { 
        // unlist this item
        $(element).removeClass("fa-eye-slash");
        $(element).addClass("fa-eye");
        $(element).parent().addClass("unlisted");
    } else { 
        // relist this item
        $(element).removeClass("fa-eye");
        $(element).addClass("fa-eye-slash");
        $(element).parent().removeClass("unlisted");
    }
}

function modalAdjust() {  
    // Adjust various things depending on mode
    // (simple list mode, matching mode, or review confirmations / disputations mode)
    // * Adjust width of score/confReason column
    // * Show or hide lock controls and confirmation panel
    // * Deactivate left / right search when not in simple list mode
    
    // By default, only allow searches on both lists at once
    var radioButtons = $("#search input");
    $(radioButtons[1]).attr("disabled", "disabled"); // left
    $(radioButtons[2]).attr("disabled", "disabled"); // right

    var mA = $('#modeSelector').val();
    if(mA === "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch" || mA === "http://127.0.0.1:8890/matchAlgorithm/disputedMatch") {  
        $('#scores').css("width", "370px");
        $('#scores').css("display", "block");
        $('.lockcontrols').css('visibility', 'hidden');
        // always lock scrolling in display-decisions mode
        if(!($('#lockcentre').hasClass('lockActive'))) { 
            handleLocks();
        }
        $(radioButtons[3]).prop("checked", true); // make sure Both is selected
    }
    else if (mA === "http://127.0.0.1:8890/matchAlgorithm/simpleList") { 
        // no scores to display on an unmatched simple listing...
        $('#scores').css("display", "none");
        // since the lists aren't matched, locked scrolling makes no sense in this mode
        $('.lockcontrols').css('visibility', 'hidden');
        if($('#lockcentre').hasClass('lockActive')) { 
            handleLocks();
        }
        // allow searches on left only / right only
        $("#search input").removeAttr("disabled");
    }
    else { 
        $('#scores').css("width", "50px");
        $('#scores').css("display", "block");
        $('.lockcontrols').css('visibility', 'visible');
        // start with locked scrolling in match modes
        if(!($('#lockcentre').hasClass('lockActive'))) { 
            handleLocks();
        }
        $(radioButtons[3]).prop("checked", true); // make sure Both is selected
        // don't reveal confirm panel since it should only show after user selects an item on each side
    }

}

function expandContextItems(thisItem) { 
    if($(thisItem).find("i").hasClass("fa-plus-square-o")) {
        // we need to expand the items
        $(thisItem).siblings(".contextItem").css("display", "block");
        // and change the icon to afford contracting rather than expanding
        $(thisItem).find("i").removeClass("fa-plus-square-o");
        $(thisItem).find("i").addClass("fa-minus-square-o");
    } else { 
        // we need to contract the items
        $(thisItem).siblings(".contextItem").css("display", "none");
        // and change the icon to afford expanding rather than contracting 
        $(thisItem).find("i").removeClass("fa-minus-square-o");
        $(thisItem).find("i").addClass("fa-plus-square-o");
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
        if(msg["confStatus"] === "http://127.0.0.1:8890/matchAlgorithm/confirmedMatch") {
            $("#confirmMatch i").removeClass("fa-cog fa-spin").addClass("fa-thumbs-up");
        } else { 
            $("#disputeMatch i").removeClass("fa-cog fa-spin").addClass("fa-thumbs-down");
        }
    });

    socket.on('bulkConfirmHandled', function(msg) {
        console.log("Bulk confirm handled: ", msg);
    });

    socket.on('contextRequestHandled', function(msg) { 
        //TODO refactor so we don't loop through the same stuff three times
        console.log("Context request handled: ", msg);
        var contextElement = $("#" + msg["leftright"]  + "Context");
        var newContextHTML = ""
        // create divs for each type of variable
        for (var i = 0; i < Object.keys(msg["results"]).length; i++) { 
            var varName = Object.keys(msg["results"])[i];
            newContextHTML += '<div class="contextVar ' + varName + '">' + '<span class="contextVarHeader" onclick="expandContextItems(this)">' + '<i class="fa fa-plus-square-o"></i> <span class="numContextItems"></span> ' + varName + '</span></div>\n';
        }
        contextElement.html(newContextHTML);
        // populate the divs
        for (var i = 0; i < Object.keys(msg["results"]).length; i++) { 
            var varName = Object.keys(msg["results"])[i];
            for(var j = 0; j < msg["results"][varName].length; j++) {
                var prevContent = $("#" + msg["leftright"] + "Context .contextVar." + varName).html();
                var newContent = '<div class="contextItem"><i class="fa fa-caret-right"></i> ' +  msg["results"][varName][j] + "</div>";
                $("#" + msg["leftright"] + "Context  .contextVar." + varName).html(prevContent + newContent);
            }
        }

        // update item counts for all variables
        for (var i = 0; i < Object.keys(msg["results"]).length; i++) { 
            var varName = Object.keys(msg["results"])[i];
            $("#" + msg["leftright"] + "Context  .contextVar." + varName + " .numContextItems").html($("#" + msg["leftright"] + "Context  .contextVar." + varName + " .contextItem").length);

        } 
    })
});
