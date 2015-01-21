#from app import app
from flask import Flask, render_template, Markup, request
from flask.ext.socketio import SocketIO, emit
import sys
from pprint import pprint
from SPARQLWrapper import SPARQLWrapper, JSON

app = Flask(__name__)
app.debug = True
***REMOVED***

socketio = SocketIO(app)

@app.route('/')
@app.route('/index')
def index():
    return render_template("index.html")

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
    saltsetA = "http://127.0.0.1:8890/saltsets/" + request.args['saltsetA']
    saltsetB = "http://127.0.0.1:8890/saltsets/" + request.args['saltsetB']
    print saltsetA
    # First grab all inter-saltset instance pairings with their scores for all matching algorithms
    sparql = SPARQLWrapper("http://127.0.0.1:8890/sparql")
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
         }}
        ORDER BY DESC(?score) ?saltAname ?saltBname """
    queryString = qS.format(saltsetA, saltsetB)
    sparql.setQuery(queryString)
    sparql.setReturnFormat(JSON)
    stringMatchResults = sparql.query().convert()

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
    # A dict containing keys for each mode (match algorithm or decision status)
    # Each has a value that is a list of dicts,
    # one dict (list item) per match
    toTemplate = dict()

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

    for result in matchDecisions["results"]["bindings"]:
        thisResult = {"matchuri": result["matchuri"]["value"],
                      "decision": result["decision"]["value"],
                      "reason": result["reason"]["value"],
                      "saltAuri": result["saltAuri"]["value"],
                      "saltAname": result["saltAname"]["value"],
                      "saltBuri": result["saltBuri"]["value"],
                      "saltBname": result["saltBname"]["value"]}
        if result["decision"]["value"] in toTemplate:
            toTemplate[result["decision"]["value"]].append(thisResult)
        else: 
            toTemplate[result["decision"]["value"]] = [thisResult]
            
    return render_template('instanceAlign.html', results = toTemplate)


@socketio.on('confirmDisputeEvent')
def socket_message(message):
    storeConfirmDispute(message)
    emit('confirmDisputeHandled', "OK!")

@socketio.on('clientConnectionEvent')
def socket_connect(message):
    print(message);


def storeConfirmDispute(message):
    message = sanitize(message)
    pprint(message)
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
	print queryString
        sparql.setQuery(queryString)
        outcome = sparql.query()
        print "Outcome of triple insert was: "
        print outcome
                
    else:
        print "Something important is missing in the message:"
        pprint(message)


def sanitize(message) : 
    # sanitize user input
    # TODO find a python library that does this properly
    for key in message:
        print key
        message[key] = str(message[key]).replace("'", "&#39;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;").replace("{", "&#123;").replace("}", "&#125;").replace("(", "&#40;").replace(")", "&#41;")
    return message

if __name__ == '__main__':
    socketio.run(app)
    app.debug = True



