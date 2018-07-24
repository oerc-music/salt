#from app import app
from flask import Flask, Response, render_template, Markup, request
from flask.ext.socketio import SocketIO, emit
from flask.ext.login import LoginManager, UserMixin, login_required, login_user, current_user
import sys
from pprint import pprint
from SPARQLWrapper import SPARQLWrapper, JSON, DIGEST
from rdflib import Graph, plugin, URIRef, Literal
from rdflib.parser import Parser
from rdflib.serializer import Serializer
import json
import re
import uuid

app = Flask(__name__)
app.debug = True
app.config['SECRET_KEY'] = 'CHANGE_ME_TO_A_USEFUL_SECRET_KEY'
app.config['SPARQLUser'] = 'SPARQL Endpoint user name'
app.config['SPARQLPassword'] = 'SPARQL Endpoint password'

login_manager = LoginManager()
login_manager.init_app(app)
socketio = SocketIO(app)

sparqlEndpoint = "http://localhost:9999/blazegraph/namespace/exemplar/sparql"

class User(UserMixin):
    # user auth stuff taken from http://gouthamanbalaraman.com/blog/minimal-flask-login-example.html
    # proxy for a proper database of users, with salted password hashes etc
    user_database = { 
        "username1": ("username1","CHANGEthisPASSW0rD!"),
	    "demo": ("demo", "demo")
    }
    
    def __init__(self, username, password):
        self.id = username
        self.password = password

    @classmethod
    def get(cls, id):
        return cls.user_database.get(id)

@login_manager.request_loader
def load_user(request):
    token = request.args.get('token')
    print "cookies: ", request.cookies
    print "token: ", token
    if token is None:
	token = request.cookies.get('token')
	print "tokenparam: ", token
    if token is None:
        token = request.headers.get('Authorization')
    if token is not None:
	try:
	    username,password = token.split(":") # naive token
	except:
	    return None
        user_entry = User.get(username)
        if(user_entry is not None):
            user = User(user_entry[0],user_entry[1])
            if(user.password == password):
                return user
    return None


@app.route('/')
@app.route('/index')
@app.route('/salt_auth')
@login_required
def index():
    response = app.make_response(render_template("index.html"))
    token = current_user.id + ":" + current_user.password
    print "Setting token: ", token
    response.set_cookie('token', token)
    return response

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
    try:
	content = re.sub(r'<([^:>]*):([^>]*)>', lambda x: '<'+context[x.group(1)]+x.group(2)+'>', content)
    except:
	content
    content += "BIND(" + weight + " as ?contextWeighting) .\n"
    content = "\n\nSELECT DISTINCT * WHERE {" + content + "\n}"
    return prefixes + content 


def contextSortedItems(saltsetA, saltsetB):
    saltsetA = saltsetA.replace("http://slobr.linkedmusic.org/saltsets/", "").replace("-","")
    saltsetB = saltsetB.replace("http://slobr.linkedmusic.org/saltsets/", "").replace("-","")
    sparql = SPARQLWrapper(sparqlEndpoint)
    sparql.setHTTPAuth(DIGEST)
    sparql.setCredentials(app.config['SPARQLUser'], app.config['SPARQLPassword'])
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
    sparql = SPARQLWrapper(sparqlEndpoint)
    sparql.setHTTPAuth(DIGEST)
    sparql.setCredentials(app.config['SPARQLUser'], app.config['SPARQLPassword'])
    sparql.setQuery("""
        PREFIX : <http://slobr.linkedmusic.org/>
        PREFIX ma: <http://slobr.linkedmusic.org/matchAlgorithm/>
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
@login_required
def instance():
    if request.args.get('saltsetA') is None or request.args.get('saltsetB') is None:
        return render_template('index.html')

    saltsetA = "http://slobr.linkedmusic.org/saltsets/" + request.args['saltsetA']
    saltsetB = "http://slobr.linkedmusic.org/saltsets/" + request.args['saltsetB']
    sparql = SPARQLWrapper(sparqlEndpoint)
    sparql.setHTTPAuth(DIGEST)
    sparql.setCredentials(app.config['SPARQLUser'], app.config['SPARQLPassword'])
    # First grab a list of all items in the two saltsets
    qS =  """
        PREFIX salt: <http://slobr.linkedmusic.org/salt/>
        PREFIX saltset: <http://slobr.linkedmusic.org/saltsets/>
        select distinct ?label ?uri ?saltset
        where {{ 
            {{
               ?uri salt:in_saltset <{0}>;
                    salt:in_saltset ?saltset ;
                    rdfs:label ?label .
            }} UNION {{
               ?uri salt:in_saltset <{1}>;
                    salt:in_saltset ?saltset ;
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
        PREFIX : <http://slobr.linkedmusic.org/>
        PREFIX ma: <http://slobr.linkedmusic.org/matchAlgorithm/>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>
        SELECT DISTINCT ?mtc ?saltA ?saltAname ?saltB ?saltBname ?score ?ma
        WHERE {{ 
            ?mtc :matchAlgorithm ?ma ;
                 :matchScore ?score .
            ?saltA :matchParticipant ?mtc ;
                 rdfs:label ?saltAname ;
                 <http://slobr.linkedmusic.org/salt/in_saltset> <{0}> .
            ?saltB :matchParticipant ?mtc ;
                 rdfs:label ?saltBname ;
                 <http://slobr.linkedmusic.org/salt/in_saltset> <{1}> .
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
    PREFIX : <http://slobr.linkedmusic.org/>
    SELECT DISTINCT ?matchuri ?saltAuri ?saltAname ?saltBuri ?saltBname ?decision ?reason ?rowlookup
    WHERE {{
        ?matchuri a :matchDecision ;
                  :matchDecisionStatus ?decision ;
		  :matchDecisionMaker "{2}" ;
                  :matchDecisionReason ?reason .
        ?saltAuri :matchParticipant ?matchuri ;
                  <http://slobr.linkedmusic.org/salt/in_saltset> <{0}> ;
                  rdfs:label ?saltAname .
        ?saltBuri :matchParticipant ?matchuri ;
                  <http://slobr.linkedmusic.org/salt/in_saltset> <{1}> ;
                  rdfs:label ?saltBname .
        BIND(CONCAT(?saltAuri, "|", ?saltBuri) as ?rowlookup) .
    }}
    ORDER BY ?saltAname ?saltBname """
    queryString = qS.format(saltsetA, saltsetB, current_user.id)
    sparql.setQuery(queryString)
    matchDecisions = sparql.query().convert()
    


    # Parse all results into a nice data structure to send to the template:
    # A dict containing keys for each mode (simple list, match algorithm or decision status)
    # Each has a value that is a list of dicts,
    # one dict (list item) per item / match
    toTemplate = dict()
    sl = "http://slobr.linkedmusic.org/matchAlgorithm/simpleList"
    for result in simpleList["results"]["bindings"]:
        if result["saltset"]["value"] == saltsetA:
            thisResult = { "lefturi":   result["uri"]["value"],
                           "leftlabel": result["label"]["value"].replace('"', "'")}
        elif result["saltset"]["value"] == saltsetB:
            thisResult = { "righturi":   result["uri"]["value"],
                           "rightlabel": result["label"]["value"].replace('"', "'")}
        else:
            print "Warning: Unexpected saltset. Found " + result["saltset"]["value"]
            print " Expected one of "+saltsetA +" or " + saltsetB
        if sl not in toTemplate:
            toTemplate[sl] = [thisResult]
        else:
            toTemplate[sl].append(thisResult)

    for result in stringMatchResults["results"]["bindings"]:
        thisResult = { "matchuri": result["mtc"]["value"],
                      "lefturi": result["saltA"]["value"],
                      "leftlabel": result["saltAname"]["value"].replace('"', "'"),
                      "righturi": result["saltB"]["value"],
                      "rightlabel": result["saltBname"]["value"].replace('"', "'"),
                      "score": result["score"]["value"]}
        if result["ma"]["value"] in toTemplate:
            toTemplate[result["ma"]["value"]].append(thisResult)
        else:
            toTemplate[result["ma"]["value"]] = [thisResult]

    cSI = "http://slobr.linkedmusic.org/matchAlgorithm/contextSortedItems"
    for result in contextSorted:
        thisResult = { "matchuri": "", # cargo cult - this is in working template
                      "rowlookup": "", # cargo cult - this is in working template
                       "lefturi": result[0] ,
                       "leftlabel": result[1].replace('"', "'"),
                       "righturi": result[2],
                       "rightlabel": result[3].replace('"', "'"),
                       "score":    result[4] }
        if cSI in toTemplate:
            toTemplate[cSI].append(thisResult)
        else:
            toTemplate[cSI] = [thisResult]

    for result in matchDecisions["results"]["bindings"]:
        thisResult = {"matchuri": result["matchuri"]["value"],
                      "rowlookup": "", # cargo cult - this is in working template
                      "confReason": result["reason"]["value"],
                      "lefturi": result["saltAuri"]["value"],
                      "leftlabel": result["saltAname"]["value"].replace('"', "'"),
                      "righturi": result["saltBuri"]["value"],
                      "rightlabel": result["saltBname"]["value"].replace('"', "'")}
        if result["decision"]["value"] in toTemplate:
            toTemplate[result["decision"]["value"]].append(thisResult)
        else: 
            toTemplate[result["decision"]["value"]] = [thisResult]

    # Finally, grab all contextual metadata for the URIs in these saltsets
    # Special prize for the first person to do all this in a single list comprehension...
    contextA = handleContextRequest({"saltset": saltsetA.replace("http://slobr.linkedmusic.org/saltsets", "")})
    saltsetAContext = {};
    for uri, params in contextA.items():
        saltsetAContext[uri] = {}
        for param, values in params.items():
            saltsetAContext[uri][param] = [{"value": entry[0], "type": entry[1]} for entry in values]
    toTemplate['saltsetAContext'] = saltsetAContext

    contextB = handleContextRequest({"saltset": saltsetB.replace("http://slobr.linkedmusic.org/saltsets", "")})
    saltsetBContext = {};
    for uri, params in contextB.items():
        saltsetBContext[uri] = {}
        for param, values in params.items():
            saltsetBContext[uri][param] = [{"value": entry[0], "type": entry[1]} for entry in values]
    toTemplate['saltsetBContext'] = saltsetBContext

    return render_template('instanceAlign.html', results = toTemplate, userid=current_user.id)


def storeConfirmDispute(message):
    message = sanitize(message)
    if message['user'] == "demo":
	return # demo users don't get to insert anything
    print "Storing " + message["aligneduri"] + " on server:"
    pprint (message);
    # Take the user's input and store it as triples
    if (message['confStatus'] and message['lefturi'] and message['righturi'] and message['aligneduri'] and message['timestamp'] and message['user']): 
        sparql = SPARQLWrapper(sparqlEndpoint)
        sparql.setHTTPAuth(DIGEST)
        sparql.setCredentials(app.config['SPARQLUser'], app.config['SPARQLPassword'])
        sparql.method = "POST"
        #Generate triples:
        turtle = """ INSERT INTO GRAPH <http://slobr.linkedmusic.org/matchDecisions/""" + app.config['SPARQLUser'] + """>
        {{
            <{0}> a <http://slobr.linkedmusic.org/matchDecision> ;
                <http://slobr.linkedmusic.org/matchDecisionStatus> '{1}' ;
                <http://slobr.linkedmusic.org/matchDecisionReason> '{2}' ;
                <http://slobr.linkedmusic.org/matchDecisionMaker> '{3}' ;
                <http://slobr.linkedmusic.org/matchURI> <{4}> ;
                <http://slobr.linkedmusic.org/matchDecisionTimestamp> '{5}' .
            <{6}> <http://slobr.linkedmusic.org/matchParticipant> <{0}> .
            <{7}> <http://slobr.linkedmusic.org/matchParticipant> <{0}> .
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

def storeRowwiseConfirm(message):
    for row in message['confRows']:
        singleMatch = dict()
        singleMatch['confStatus'] = message['confStatus']
        singleMatch['confReason'] = message['confReason']
        singleMatch['user'] = message['user']
        singleMatch['timestamp'] = message['timestamp']
        #FIXME - should use consistantly use matchuri or aligneduri across SALT
        singleMatch['aligneduri'] = row['matchuri']
        singleMatch['lefturi'] = row['lefturi']
        singleMatch['leftlabel'] = row['leftlabel']
        singleMatch['righturi'] = row['righturi']
        singleMatch['rightlabel'] = row['rightlabel']
        storeConfirmDispute(singleMatch)
    #TODO also store information on bulk nature of this all

def handleContextRequest(message):
    contextQuery = open("sparql" + message["saltset"] + "_context.rq").read() #TODO validate filename first
    if "uri" in message: # specific context request - specify the uri we are given
        contextQuery = contextQuery.format("BIND(<" + message["uri"] + "> AS ?uri) .")
    else: #general context request - select all uris
        contextQuery = contextQuery.format("")

    sparql = SPARQLWrapper(sparqlEndpoint)
    sparql.setHTTPAuth(DIGEST)
    sparql.setCredentials(app.config['SPARQLUser'], app.config['SPARQLPassword'])
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

@socketio.on("rowwiseConfirmEvent")
def socket_rowwiseConfirm(message):
    storeRowwiseConfirm(message)
    emit('rowwiseConfirmHandled', message)

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
        message[key] = message[key].encode('utf-8');
        message[key] = message[key].replace("'", "&#39;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;").replace("{", "&#123;").replace("}", "&#125;").replace("(", "&#40;").replace(")", "&#41;").replace(";", "&#59;");
    return message



if __name__ == '__main__':
    socketio.run(app, port=4000)
    app.debug = False



