#from app import app
from flask import Flask, render_template, Markup
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
    sparql = SPARQLWrapper("http://127.0.0.1:8890/sparql")
    sparql.setQuery("""
        PREFIX : <http://127.0.0.1:8890/>
        PREFIX ma: <http://127.0.0.1:8890/matchAlgorithm/>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>
        SELECT DISTINCT ?emsname ?slickname ?score ?ma
        WHERE { 
            ?mtc a :fuzzyMatch ;
                 :matchAlgorithm ?ma ;
                 :matchScore ?score .
            ?ems :matchParticipant ?mtc ;
                 dc:contributor ?emsname .
            ?slick :matchParticipant ?mtc ;
                 rdfs:label ?slickname .
         }
    """)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    pprint(results)
    output = "<table><tr><td>EMS Name</td><td>SLICKMEM Name</td><td>Score</td><td>Algorithm</td></tr>"
    for result in results["results"]["bindings"]:
        output += "<tr>"
        output += "<td>" + result["emsname"]["value"] + "</td>"
        output += "<td>" + result["slickname"]["value"] + "</td>"
        output += "<td>" + result["score"]["value"] + "</td>"
        output += "<td>" + result["ma"]["value"] + "</td>"
        output += "</tr>"

    output += "</table>"


    results = { 'nrow' : len(results["results"]["bindings"]),
                'prettyprint' : output }
    return render_template('index.html', results=results)
    

@app.route('/instance')
def instance():
    # First grab all EMS - SLICK pairings with their scores for all algorithms
    sparql = SPARQLWrapper("http://127.0.0.1:8890/sparql")
    sparql.setQuery("""
        PREFIX : <http://127.0.0.1:8890/>
        PREFIX ma: <http://127.0.0.1:8890/matchAlgorithm/>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>
        SELECT DISTINCT ?mtc ?ems ?emsname ?slick ?slickname ?score ?ma
        WHERE { 
            ?mtc :matchAlgorithm ?ma ;
                 :matchScore ?score .
            ?ems :matchParticipant ?mtc ;
                 dc:contributor ?emsname .
            ?slick :matchParticipant ?mtc ;
                 rdfs:label ?slickname .
         } 
        ORDER BY DESC(?score) ?emsname ?slickname
    """)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    # Parse into a nice data structure to send to the template:
    # A dict containing keys for each match algorithm
    # Each has a value that is a list of dicts,
    # one dict (list item) per match
    toTemplate = dict()
    for result in results["results"]["bindings"]:
        thisResult = { "matchuri": result["mtc"]["value"],
                      "emsuri": result["ems"]["value"],
                      "emsname": result["emsname"]["value"],
                      "slickuri": result["slick"]["value"],
                      "slickname": result["slickname"]["value"],
                      "score": result["score"]["value"]}
        if result["ma"]["value"] in toTemplate:
            toTemplate[result["ma"]["value"]].append(thisResult)
        else:
            toTemplate[result["ma"]["value"]] = [thisResult]
            
    return render_template('instanceAlign.html', results = toTemplate)


@socketio.on('confirmDisconfirmEvent')
def socket_message(message):
    storeConfirmDisconfirm(message)
    emit('confirmDisconfirmHandled', "OK!")

@socketio.on('clientConnectionEvent')
def socket_connect(message):
    print(message);


def storeConfirmDisconfirm(message):
    print "Okay! lalala"
    pprint(message)
    # Take the user's input
    # ideally, sanitize it a bit
    # and store it as triples
    if (message['confStatus'] and message['lefturi'] and message['righturi'] and message['aligneduri'] and message['timestamp'] and message['user']): 
        print ("HERE WE GO: ", message['aligneduri'], message['confStatus'], message['confReason'], message['user'], message['aligneduri'], message['timestamp'], message['lefturi'], message['righturi'] )
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

if __name__ == '__main__':
    socketio.run(app)
