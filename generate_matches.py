#!/usr/bin/python

import sys
import warnings
from fuzzywuzzy import fuzz
import uuid
from pprint import pprint
from SPARQLWrapper import SPARQLWrapper, JSON

warnings.filterwarnings('error') # turn warnings into exceptions

def main(): 
    if len(sys.argv) < 3: 
        raise KeyError('Please invoke me with at least two SPARQL query files as arguments')

    queryResults = dict()

    threshold = 80 #have to match or beat this score for inclusion in the results

    sparql = SPARQLWrapper("http://127.0.0.1:8890/sparql")
    sparql.setReturnFormat(JSON)
    for filename in sys.argv[1:]:
        queryFromFile = open(filename).read()
        try:
            sparql.setQuery(queryFromFile)
            queryResults[filename] = sparql.query().convert()
        except: 
            raise Exception("Problem with SPARQL input file: " + filename)


    datasetDicts = dict()
    for dataset in queryResults:
        # There's a valid use case where the user might want to align a dataset to itself, i.e.
        # have the same data appear on the left and right side in SALT
        # so make sure not to overwrite anything
        if(dataset in datasetDicts): 
            continue
        datasetDicts[dataset] = dict()
        # There are some instances where multiple URIs share the same composer name (label)
        # Either because of genuine repeated names of different individuals
        # or because of error in the data set
        # Either way, retain all versions by storing the URIs as a list, indexed by label 
        for result in queryResults[dataset]["results"]["bindings"]:
            try:
                label = result["label"]["value"]
            except KeyError: 
                pprint(result)
                raise KeyError("Problem in dataset: " + dataset + "; ensure that your SPARQL query is binding to the variables ?label and ?uri")

            if label in datasetDicts[dataset]:
                datasetDicts[dataset][label].append(result["uri"]["value"])
            else:
                datasetDicts[dataset][label] = [result["uri"]["value"]]


    # Iterate through every two-item combination of items in our list of data sets
    # and figure out the intersections and differences (in order to determine exact vs fuzzy matches)
    combinations = list()
    for i in range(len(datasetDicts)):
        for j in range(i+1, len(datasetDicts)): 
            a = sorted(datasetDicts.keys())[i]
            b = sorted(datasetDicts.keys())[j]
            doMatches(datasetDicts[a], datasetDicts[b], threshold)

    # Now iterate through the list one more time and determine within-dataset matches for each set
    for dataset in datasetDicts:
        doMatches(datasetDicts[dataset], datasetDicts[dataset], threshold)


def doMatches(a, b, threshold):
        aSet = set(a.keys())
        bSet = set(b.keys())
        inboth = list(aSet.intersection(bSet))

        onlya = list(aSet.difference(bSet))
        onlyb =list(bSet.difference(aSet))
        #Now generate triples encoding the distance measure on the URI (rather than label) level
        # First do the perfect matches:
        for label in inboth:
            for aURI in a[label]:
                for bURI in b[label]:
                    turtle = """
                        {0} a <http://slobr.linkedmusic.org/exactMatch> ;
                            <http://slobr.linkedmusic.org/matchScore> 100 ;
                            <http://slobr.linkedmusic.org/matchAlgorithm> <http://slobr.linkedmusic.org/matchAlgorithm/exactMatch> .
                        {1} <http://slobr.linkedmusic.org/matchParticipant> {0} .
                        {2} <http://slobr.linkedmusic.org/matchParticipant> {0} .
                    """
                    # make up a matchuri based on the URIs of the two entities to be matched and the algo used
                    matchuri = "<http://slobr.linkedmusic.org/matchRelation/{0}>".format(str(uuid.uuid4()))
#                           ( "<http://slobr.linkedmusic.org/matchRelation/" + 
#                           aURI.replace("http://", "").replace("/", "--") + 
#                           "---" +
#                           bURI.replace("http://", "").replace("/","--") + 
#                           "---" + "slobr.linkedmusic.org/matchAlgorithm/exactMatch".replace("/", "--") + 
#                           ">" )
                    print(turtle.format(matchuri, "<" + aURI + ">", "<" + bURI + ">"))
            

        #Determine distance measures...
        fuzzratios = set()
        for ems in onlya:
            for slick in onlyb:
                simple_ratio = fuzz.ratio(ems, slick)
                partial_ratio = fuzz.partial_ratio(ems, slick)
                token_sort_ratio = fuzz.token_sort_ratio(ems, slick)
                token_set_ratio = fuzz.token_set_ratio(ems, slick)
                for aURI in a[ems] :
                    for bURI in b[slick]: 
                        if simple_ratio >= threshold: fuzzratios.add((aURI, bURI, simple_ratio, 'simple')) 
                        if partial_ratio >= threshold: fuzzratios.add((aURI, bURI, partial_ratio, 'partial')) 
                        if token_sort_ratio >= threshold: fuzzratios.add((aURI, bURI, token_sort_ratio, 'token-sort')) 
                        if token_set_ratio >= threshold: fuzzratios.add((aURI, bURI, token_set_ratio, 'token-set')) 

        # Now do the fuzzy matches
        for match in fuzzratios:
            turtle = """
                {0} a <http://slobr.linkedmusic.org/fuzzyMatch> ;
                    <http://slobr.linkedmusic.org/matchAlgorithm> <http://slobr.linkedmusic.org/matchAlgorithm/fuzzywuzzy_{4}-ratio> ;
                    <http://slobr.linkedmusic.org/matchScore> {3} .
                {1} <http://slobr.linkedmusic.org/matchParticipant> {0} .
                {2} <http://slobr.linkedmusic.org/matchParticipant> {0} .
            """
            matchuri = "<http://slobr.linkedmusic.org/matchRelation/{0}>".format(str(uuid.uuid4()))
#            matchuri = ( 
#                    "<http://slobr.linkedmusic.org/matchRelation/" + 
#                   match[0].replace("http://", "").replace("/", "--") + 
#                   "---" +
#                   match[1].replace("http://", "").replace("/","--") + 
#                   "---" + 
#                   match[3].replace("http://", "").replace("/","--") + 
#                   ">" )
            print(turtle.format(matchuri, "<" + match[0] + ">", "<" + match[1] + ">", match[2], match[3])) 



if __name__ == "__main__":
    main()
