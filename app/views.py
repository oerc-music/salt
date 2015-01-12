from app import app
from flask import render_template, Markup
import sys
from pprint import pprint
from SPARQLWrapper import SPARQLWrapper, JSON

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
