#from app import app
from flask import Flask, render_template, Markup, request
from flask.ext.socketio import SocketIO, emit
import sys
from pprint import pprint
from SPARQLWrapper import SPARQLWrapper, JSON
from rdflib import Graph, plugin, URIRef, Literal
from rdflib.parser import Parser
from rdflib.serializer import Serializer
import json
import re
import uuid

app = Flask(__name__)
app.debug = True
***REMOVED***

socketio = SocketIO(app)

@app.route('/')
@app.route('/index')
def index():
    return render_template("index.html")

@app.route('/config')
def render_config():
    confile = open('config.jsonld')
    confjson = json.load(confile)
    confile.close()
    context = confjson["@context"]
    sparql = ""
    for relation in confjson["salt:relation"]:
        for contextItem in relation["salt:hasContextItem"]:
            contextItem["@context"] = context
            sparql += "\n\n--------\n\n" + contextPathsToSPARQL(contextItem["salt:contextPath"], contextItem["salt:contextWeighting"], confjson["@context"]) 
    g = Graph().parse(data=json.dumps(confjson), format="json-ld")
    as_triples = g.serialize(format="turtle", context=context)
    return render_template('config.html', sparql=sparql, currentConfig=as_triples, jsonConfig = json.dumps(confjson, indent=2) )

def read_config(saltsetA, saltsetB): 
    confile = open('config.jsonld')
    confjson = json.load(confile)
    confile.close()
    context = confjson["@context"]
    for relation in confjson["salt:relation"]:
        relatedSets = list(map(lambda y: y["@id"], relation["salt:relatesSet"]))
        if "saltsets:"+saltsetA in relatedSets and "saltsets:"+saltsetB in relatedSets:
            break  # found our relation in the config file
    try: 
        contextItemList = relation["salt:hasContextItem"]
        for contextItem in contextItemList:
            contextItem["@context"] = context
        return contextItemList
    except:
        return [] # misconfigured

def contextPathsToSPARQL(cPaths, weight, context):
    g = Graph().parse(data=json.dumps(cPaths), format="json-ld")
    as_triples = g.serialize(format="turtle")
    prefixes = []
    content = []
    for line in as_triples.split("\n"):
        if line.startswith("@prefix"): 
            matches = re.findall(r'@prefix (\w+:) <(\w+):> .', line)
            if matches:
                prefixes.append('PREFIX ' + matches[0][0] + ' <' + context[matches[0][1]]+'>')
        else: content.append(line)
    prefixes = "\n".join(prefixes)       
    content = "\n".join(content)
    #replace list item place holders with SPARQL vars
    content = re.sub(r'<listitem:([^>]+)> a \w+:listItem\s*;\s*\n', lambda x: '?' + x.group(1), content) 
    content = re.sub(r'<listitem:([^>]+)>', lambda x: '?' + x.group(1), content) 
    #replace all blank nodes with SPARQL vars
    content = content.replace("_:", "?")
    content = re.sub(r'<([^:>]*):([^>]*)>', lambda x: '<'+context[x.group(1)]+x.group(2)+'>', content)
    content += "BIND(" + weight + " as ?contextWeighting) .\n"
    content = "\n\nSELECT * WHERE {" + content + "\n}"
    return prefixes + content 


def contextSortedItems(saltsetA, saltsetB):
    saltsetA = saltsetA.replace("http://127.0.0.1:8890/saltsets/", "")
    saltsetB = saltsetB.replace("http://127.0.0.1:8890/saltsets/", "")
    sparql = SPARQLWrapper("http://127.0.0.1:8890/sparql")
    sparql.setReturnFormat(JSON)
    contextItemList = read_config(saltsetA, saltsetB)
    
    allResults = []
    aggregate = dict()
    for contextItem in contextItemList:
        sparql.setQuery(contextPathsToSPARQL(contextItem["salt:contextPath"], contextItem["salt:contextWeighting"], contextItem["@context"]))
        theseResults = sparql.query().convert()
        for thisResult in theseResults["results"]["bindings"]:
            allResults.append(thisResult)
    for result in allResults:
        try:
            thisKey = (result[saltsetA]["value"], result[saltsetB]["value"])
            if thisKey in aggregate:
                aggregate[thisKey]["contextWeighting"] += float(result["contextWeighting"]["value"])
            else:
                aggregate[thisKey] = {saltsetA: result[saltsetA]["value"], "saltsetAlabel": result[saltsetA+"_label"]["value"], saltsetB: result[saltsetB]["value"], "saltsetBlabel": result[saltsetB + "_label"]["value"], "contextWeighting": float(result["contextWeighting"]["value"])}
        except KeyError:
                print "Saltset relation not configured: ", saltsetA, " : ", saltsetB
                return []
    byContextWeighting = sorted(aggregate, key=lambda k: aggregate[k]["contextWeighting"], reverse=True)
    contextSortedItems = []
    for ix, item in enumerate(byContextWeighting):
        contextSortedItems.append((byContextWeighting[ix][0], aggregate[item]["saltsetAlabel"], byContextWeighting[ix][1],aggregate[item]["saltsetBlabel"], aggregate[item]["contextWeighting"]))
    return contextSortedItems


@app.route('/dump')
def dump():
    sparql = SPARQLWrapper("http://127.0.0.1:8890/sparql")
    sparql.setQuery("""
        PREFIX : <http://127.0.0.1:8890/>
        PREFIX ma: <http://127.0.0.1:8890/matchAlgorithm/>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>
        SELECT DISTINCT ?saltAname ?saltBname ?score ?ma
        WHERE { 
            ?mtc a :fuzzyMatch ;
                 :matchAlgorithm ?ma ;
                 :matchScore ?score .
            ?saltA :matchParticipant ?mtc ;
                 rdfs:label ?saltAname .
            ?saltB :matchParticipant ?mtc ;
                 rdfs:label ?saltBname .
         }
    """)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    pprint(results)
    output = "<table><tr><td>Salt A Name</td><td>Salt B Name</td><td>Score</td><td>Algorithm</td></tr>"
    for result in results["results"]["bindings"]:
        output += "<tr>"
        output += "<td>" + result["saltAname"]["value"] + "</td>"
        output += "<td>" + result["saltBname"]["value"] + "</td>"
        output += "<td>" + result["score"]["value"] + "</td>"
        output += "<td>" + result["ma"]["value"] + "</td>"
        output += "</tr>"

    output += "</table>"


    results = { 'nrow' : len(results["results"]["bindings"]),
                'prettyprint' : output }
    return render_template('dump.html', results=results)
    


@app.route('/instance', methods=["GET"])
@app.route('/salt', methods=["GET"])
def instance():
    if request.args.get('saltsetA') is None or request.args.get('saltsetB') is None:
        return render_template('index.html')

    saltsetA = "http://127.0.0.1:8890/saltsets/" + request.args['saltsetA']
    saltsetB = "http://127.0.0.1:8890/saltsets/" + request.args['saltsetB']
    sparql = SPARQLWrapper("http://127.0.0.1:8890/sparql")
    # First grab a list of all items in the two saltsets
    qS =  """
        PREFIX salt: <http://127.0.0.1:8890/salt/>
        PREFIX saltset: <http://127.0.0.1:8890/saltsets/>
        select ?label ?uri ?saltset
        where {{ 
            {{
               ?uri salt:in_salt_set <{0}>;
                    salt:in_salt_set ?saltset ;
                    rdfs:label ?label .
            }} UNION {{
               ?uri salt:in_salt_set <{1}>;
                    salt:in_salt_set ?saltset ;
                    rdfs:label ?label .
            }}
        }}
        ORDER BY ?saltset ?label """
    queryString = qS.format(saltsetA, saltsetB)
    sparql.setQuery(queryString) 
    sparql.setReturnFormat(JSON)
    simpleList = sparql.query().convert()

    #Then grab all inter-saltset instance pairings with their scores for all matching algorithms
    qS =  """
        PREFIX : <http://127.0.0.1:8890/>
        PREFIX ma: <http://127.0.0.1:8890/matchAlgorithm/>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>
        SELECT DISTINCT ?mtc ?saltA ?saltAname ?saltB ?saltBname ?score ?ma
        WHERE {{ 
            ?mtc :matchAlgorithm ?ma ;
                 :matchScore ?score .
            ?saltA :matchParticipant ?mtc ;
                 rdfs:label ?saltAname ;
                 <http://127.0.0.1:8890/salt/in_salt_set> <{0}> .
            ?saltB :matchParticipant ?mtc ;
                 rdfs:label ?saltBname ;
                 <http://127.0.0.1:8890/salt/in_salt_set> <{1}> .
            #FILTER(?saltA != ?saltB)
         }}
        ORDER BY DESC(?score) ?saltAname ?saltBname """
    queryString = qS.format(saltsetA, saltsetB)
    sparql.setQuery(queryString)
    stringMatchResults = sparql.query().convert()

    # Now grab all contextual match information for these saltsets, as configured in config.jsonld
    contextSorted = contextSortedItems(saltsetA, saltsetB)

    # Now grab any match decisions (confirmations/disputations) established in previous sessions
    qS = """
    PREFIX : <http://127.0.0.1:8890/>
    SELECT DISTINCT ?matchuri ?saltAuri ?saltAname ?saltBuri ?saltBname ?decision ?reason 
    WHERE {{
        ?matchuri a :matchDecision ;
                  :matchDecisionStatus ?decision ;
                  :matchDecisionReason ?reason .
        ?saltAuri :matchParticipant ?matchuri ;
                  <http://127.0.0.1:8890/salt/in_salt_set> <{0}> ;
                  rdfs:label ?saltAname .
        ?saltBuri :matchParticipant ?matchuri ;
                  <http://127.0.0.1:8890/salt/in_salt_set> <{1}> ;
                  rdfs:label ?saltBname .
    }}
    ORDER BY ?saltAname ?saltBname """
    queryString = qS.format(saltsetA, saltsetB)
    sparql.setQuery(queryString)
    matchDecisions = sparql.query().convert()
    


    # Parse all results into a nice data structure to send to the template:
    # A dict containing keys for each mode (simple list, match algorithm or decision status)
    # Each has a value that is a list of dicts,
    # one dict (list item) per item / match
    toTemplate = dict()
    sl = "http://127.0.0.1:8890/matchAlgorithm/simpleList"
    for result in simpleList["results"]["bindings"]:
        thisResult = { "uri": result["uri"]["value"],
                       "label": result["label"]["value"],
                       "saltset": result["saltset"]["value"]}
        if sl not in toTemplate:
            toTemplate[sl] = [thisResult]
        else:
            toTemplate[sl].append(thisResult)

    for result in stringMatchResults["results"]["bindings"]:
        thisResult = { "matchuri": result["mtc"]["value"],
                      "saltAuri": result["saltA"]["value"],
                      "saltAname": result["saltAname"]["value"],
                      "saltBuri": result["saltB"]["value"],
                      "saltBname": result["saltBname"]["value"],
                      "score": result["score"]["value"]}
        if result["ma"]["value"] in toTemplate:
            toTemplate[result["ma"]["value"]].append(thisResult)
        else:
            toTemplate[result["ma"]["value"]] = [thisResult]

    cSI = "http://127.0.0.1:8890/matchAlgorithm/contextSortedItems"
    for result in contextSorted:
        thisResult = { "saltAuri": result[0] ,
                       "saltAname": result[1] ,
                       "saltBuri": result[2],
                       "saltBname": result[3],
                       "score":    result[4] }
        if cSI in toTemplate:
            toTemplate[cSI].append(thisResult)
        else:
            toTemplate[cSI] = [thisResult]

    for result in matchDecisions["results"]["bindings"]:
        thisResult = {"matchuri": result["matchuri"]["value"],
                      "decision": result["decision"]["value"],
                      "confReason": result["reason"]["value"],
                      "saltAuri": result["saltAuri"]["value"],
                      "saltAname": result["saltAname"]["value"],
                      "saltBuri": result["saltBuri"]["value"],
                      "saltBname": result["saltBname"]["value"]}
        if result["decision"]["value"] in toTemplate:
            toTemplate[result["decision"]["value"]].append(thisResult)
        else: 
            toTemplate[result["decision"]["value"]] = [thisResult]
    
    # Finally, grab all contextual metadata for the URIs in these saltsets
    toTemplate["saltsetAContext"] = handleContextRequest({"saltset": saltsetA.replace("http://127.0.0.1:8890/saltsets", "")})
    toTemplate["saltsetBContext"] = handleContextRequest({"saltset": saltsetB.replace("http://127.0.0.1:8890/saltsets", "")})

    return render_template('instanceAlign.html', results = toTemplate)


def storeConfirmDispute(message):
    message = sanitize(message)
    print "Storing " + message["aligneduri"] + " on server:"
    pprint (message);
    # Take the user's input and store it as triples
    if (message['confStatus'] and message['lefturi'] and message['righturi'] and message['aligneduri'] and message['timestamp'] and message['user']): 
        sparql = SPARQLWrapper("http://127.0.0.1:8890/sparql")
        sparql.method = "POST"
        #Generate triples:
        turtle = """ INSERT INTO GRAPH <http://127.0.0.1:8890/matchDecisions>
        {{
            <{0}> a <http://127.0.0.1:8890/matchDecision> ;
                <http://127.0.0.1:8890/matchDecisionStatus> '{1}' ;
                <http://127.0.0.1:8890/matchDecisionReason> '{2}' ;
                <http://127.0.0.1:8890/matchDecisionMaker> '{3}' ;
                <http://127.0.0.1:8890/matchURI> <{4}> ;
                <http://127.0.0.1:8890/matchDecisionTimestamp> '{5}' .
            <{6}> <http://127.0.0.1:8890/matchParticipant> <{0}> .
            <{7}> <http://127.0.0.1:8890/matchParticipant> <{0}> .
        }}"""
	queryString = turtle.format(message['aligneduri'], message['confStatus'], message['confReason'], message['user'], message['aligneduri'], message['timestamp'], message['lefturi'], message['righturi'])
        print(queryString)
        sparql.setQuery(queryString)
        outcome = sparql.query()
        print "Outcome of triple insert was: "
        print outcome
                
    else:
        print "Something important is missing in the message:"
        pprint(message)

def storeBulkConfirm(message):
    print("Bulk confirm called with")
    for match in message['matches']:
        singleMatch = dict()
        singleMatch['confStatus'] = message['confStatus']
        singleMatch['confReason'] = message['confReason']
        singleMatch['user'] = message['user']
        singleMatch['timestamp'] = message['timestamp']
        singleMatch['aligneduri'] = match['aligneduri']
        singleMatch['lefturi'] = match['lefturi']
        singleMatch['leftlabel'] = match['leftlabel']
        singleMatch['righturi'] = match['righturi']
        singleMatch['rightlabel'] = match['rightlabel']
        storeConfirmDispute(singleMatch)
    #TODO also store information on bulk nature of this all

def handleContextRequest(message):
    contextQuery = open("sparql/" + message["saltset"] + "_context.rq").read() #TODO validate filename first
    if "uri" in message: # specific context request - specify the uri we are given
        contextQuery = contextQuery.format("BIND(<" + message["uri"] + "> AS ?uri) .")
    else: #general context request - select all uris
        contextQuery = contextQuery.format("")

    sparql = SPARQLWrapper("http://127.0.0.1:8890/sparql")
    sparql.setReturnFormat(JSON)
    sparql.setQuery(contextQuery)
    try:
        outcome = sparql.query().convert()
    except Exception as e: 
        print "Encountered error trying to execute fetch context query: {0}" + str(e)
        return
    if "uri" in message: #specific context request - return as sets
        literals = set()
        uris = set()
        for item in outcome["results"]["bindings"]:
            for param in item:
                if item[param]["type"] == "literal":
                    literals.add( (param, item[param]["value"]) )
                elif item[param]["type"] == "uri":
                    uris.add( (param, item[param]["value"]) )
        return {"literals": list(literals), "uris":list(uris)}
    else: #general context request - return uri-keyed dictionary of param:item_set tuples
        # we are using item sets here in order to achieve distinct values for each parameter
        results = dict()
        for item in outcome["results"]["bindings"]:
            for param in item:
                if item["uri"]["value"] not in results:
                    results[item["uri"]["value"]] = dict()
                if param not in results[item["uri"]["value"]]:
                    results[item["uri"]["value"]][param] = set()
                results[item["uri"]["value"]][param].add((item[param]["value"], item[param]["type"]))
        
        return results


@socketio.on('confirmDisputeEvent')
def socket_confirmDispute(message):
    storeConfirmDispute(message)
    emit('confirmDisputeHandled', message) 

@socketio.on("bulkConfirmEvent")
def socket_bulkConfirm(message):
    storeBulkConfirm(message)
    for match in message['matches']:
        match['confStatus'] = message['confStatus']
        match['confReason'] = message['confReason']
        match['user'] = message['user']
        match['timestamp'] = message['timestamp']
        emit('confirmDisputeHandled', match)
    emit('bulkConfirmHandled', message)

@socketio.on('clientConnectionEvent')
def socket_connect(message):
    print(message)

@socketio.on('specificContextRequest')
def socket_context_request(message):
    try: 
        response = dict()
        response["leftright"] = message["leftright"]
        response["results"] = handleContextRequest(message)
        emit('specificContextRequestHandled', response);
        print "Specific context request handled!"
        pprint(response["results"])
    except:
        emit('specificContextRequestFailed')

@socketio.on('generalContextRequest')
def general_context_request(message):
    response = dict()
    response["left"] = handleContextRequest({"saltset": message["saltsetA"]});
    response["right"] = handleContextRequest({"saltset": message["saltsetB"]});
    emit('generalContextRequestHandled', response)

    
def sanitize(message) : 
    # sanitize user input
    # TODO find a python library that does this properly
    for key in message:
        message[key] = str(message[key]).replace("'", "&#39;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;").replace("{", "&#123;").replace("}", "&#125;").replace("(", "&#40;").replace(")", "&#41;").replace(";", "&#59;");
    return message



if __name__ == '__main__':
    socketio.run(app)
    app.debug = True



