# energymodel
collects building geometry from 3D bag. cleans data, runs energy plus simulations, outputs annual heating and cooling demands per floor area, collects outputs for training ANN. 

using python 3.13.3 in vs studio

1. DATA GENERATION + PROCESSING

0: ouput archetype ids from excel to json
1: retrieve pand ids from 3D bag
2: define surface types from vertices
3: map materials for each archetype id from excel to json
4: write idf file
5: run energy plus simulation
6: process energy demands for heating and cooling as annual kwh/m2
7: create final output json with building features and energy demands

2. DATA PROCESSING

8. flatten json features to csv
9. 
