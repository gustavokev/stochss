""" 
Code based off StochSS internal interface to StochKit, originally by 
A. Hellander. Stand-alone GillesPy module work by J. Abel and B. Drawert.

Version 0.1 on github as of 12-4-2014.
    
"""

from collections import OrderedDict
import scipy as sp
import numpy as np
import matplotlib.pyplot as plt
import tempfile
import uuid
import subprocess
import types
import random

try:
    import lxml.etree as etree
    no_pretty_print = False
except:
    import xml.etree.ElementTree as etree
    import xml.dom.minidom
    import re
    no_pretty_print = True

try:
    import scipy.io as spio
    isSCIPY = True
except:
    pass

import os
import sys
try:
    import shutil
    import numpy
except:
    pass

import pdb


def import_SBML(filename, name=None, gillespy_model=None):
    """ SBML to GillesPy model converter. NOTE: non-mass-action rates
    in terms of concentrations may not be converted for population 
    simulation"""
    
    try:
        from gillespy.SBMLimport import convert
    except ImportError:
        raise ImportError('SBML conversion not imported successfully')
        
    return convert(filename, modelName = name, gillespy_model = gillespy_model)



class Model(object):
    """
    Representation of a well mixed biochemical model. Contains reactions,
    parameters, species, etc.
    
    """
    
    def __init__(self, name="", volume=1.0, population = True):
        """ Create an empty model. """
        
        # The name that the model is referenced by (should be a String)
        self.name = name
        
        # Optional decription of the model (string)
        self.annotation = ""
        
        # Dictionaries with Species, Reactions and Parameter objects.
        # Species,Reactio and Paramter names are used as keys.
        self.listOfParameters = OrderedDict()
        self.listOfSpecies    = OrderedDict()
        self.listOfReactions  = OrderedDict()

        # This defines the unit system at work for all numbers in the model
        #   It should be a logical error to leave this undefined, subclasses should set it
        if population == True:
            self.units = "population"
        else: 
            self.units = "concentration"
            if volume != 1.0:
                raise Warning("Concentration models account for volume implicitly,explicit volume definition is not required. Note: concentration models may only be simulated deterministically.")
        
        self.volume = volume
        
        # Dict that holds flattended parameters and species for
        # evaluation of expressions in the scope of the model.
        self.namespace = OrderedDict([])
        
        # These are defaults for simulation, and yes it is a bit weired to have them here.
        #self.t = 20
        #self.increment = 0.05
        self.timespan(numpy.linspace(0,20,401))
        
    
    def serialize(self):
        """ Serializes a Model object to valid StochML. """
        self.resolve_parameters()
        doc = StochMLDocument().from_model(self)
        return doc.to_string()
    
    def update_namespace(self):
        """ Create a dict with flattened parameter and species objects. """
        self.namespace = OrderedDict([])
        for param in self.listOfParameters:
            self.namespace[param]=self.listOfParameters[param].value
        # Dictionary of expressions that can be evaluated in the scope of this
        # model.
        self.expressions = {}

    def get_species(self, sname):
        return self.listOfSpecies[sname]
    
    def get_all_species(self):
        return self.listOfSpecies

    def add_species(self, obj):
        """ 
            Add a species to listOfSpecies. Accepts input either as a single 
            Species object, or as a list of Species objects.
        """
                
        if isinstance(obj, Species):
            if obj.name in self.listOfSpecies:
                raise ModelError("Can't add species. A species with that \
                                    name alredy exisits.")
            self.listOfSpecies[obj.name] = obj;
        else: # obj is a list of species
            for S in obj:
                if S.name in self.listOfSpecies:
                    raise ModelError("Can't add species. A species with that \
                                        name alredy exisits.")
                self.listOfSpecies[S.name] = S;
        return obj

    
    def delete_species(self, obj):
        self.listOfSpecies.pop(obj)        
         
    def delete_all_species(self):
        self.listOfSpecies.clear()

    def set_units(self, units):
        if units.lower() == 'concentration' or units.lower() == 'population':
            self.units = units.lower()
        else:
            raise ModelError("units must be either concentration or \
                                population (case insensitive)")

    def get_parameter(self,pname):
        try:
            return self.listOfParameters[pname]
        except:
            raise ModelError("No parameter named "+pname)
    def get_all_parameters(self):
        return self.listOfParameters
    
    def add_parameter(self,params):
        """ 
            Add Paramter(s) to listOfParamters. Input can be either a
            single paramter object or a list of Parameters.
        """
        # TODO, make sure that you don't overwrite an existing parameter??
        if type(params).__name__=='list':
            for p in params:
                self.listOfParameters[p.name] = p
        else:
            if type(params).__name__=='instance':
                self.listOfParameters[params.name] = params
            else:
                raise
        return params

    def delete_parameter(self, obj):
        self.listOfParameters.pop(obj)

    def set_parameter(self,pname,expression):
        """ Set the expression of an existing paramter. """
        p = self.listOfParameters[pname]
        p.expression = expression
        p.evaluate()
        
    def resolve_parameters(self):
        """ Attempt to resolve all parameter expressions to scalar floats. 
        This methods must be called before exporting the model. """
        self.update_namespace()
        for param in self.listOfParameters:
            try:
                self.listOfParameters[param].evaluate(self.namespace)
            except:
                raise ParameterError("Could not resolve Parameter expression "
                                        + param + "to a scalar value.")
    
    def delete_all_parameters(self):
        self.listOfParameters.clear()

    def add_reaction(self,reacs):
        """ Add reactions to model. Input can be single instance, a list
        of instances or a dict with name,instance pairs. """
        
        # TODO, make sure that you cannot overwrite an existing parameter
        param_type = type(reacs).__name__
        if param_type == 'list':
            for r in reacs:
                self.listOfReactions[r.name] = r
        elif param_type == 'dict' or param_type == 'OrderedDict':
            self.listOfReactions = reacs
        elif param_type == 'instance':
                self.listOfReactions[reacs.name] = reacs
        else:
            raise
        return reacs

    def timespan(self, tspan):
        """ Set the time span of simulation. Since StochKit does not support 
            non-uniform timespans, we raise an error in that case. In future,
            we will work around this. """
        
        items = numpy.diff(tspan)
        items = map(lambda x: round(x, 10),items)
        isuniform = (len(set(items)) == 1)
        
        if isuniform:
            self.tspan = tspan
        else:
            raise InvalidModelError("StochKit only supports uniform timespans")

    def get_reaction(self, rname):
        return self.listOfReactions[rname]

    def get_all_reactions(self):
        return self.listOfReactions
    
    def delete_reaction(self, obj):
        self.listOfReactions.pop(obj)
        
    def delete_all_reactions(self):
        self.listOfReactions.clear()

    def run(self, number_of_trajectories=1, seed=None, report_level=0, solver=None, stochkit_home=None, debug=False, show_labels=False):
        if solver is not None:
            if isinstance(solver, (type, types.ClassType)) and  issubclass(solver, GillesPySolver):
                return solver.run(self,t=self.tspan[-1],increment=self.tspan[-1]-self.tspan[-2],seed=seed,number_of_trajectories=number_of_trajectories, stochkit_home=stochkit_home, debug=debug, show_labels=show_labels)
            else:
                raise SimuliationError('argument "solver" to run() must be a subclass of GillesPySolver')
        else:
            return StochKitSolver.run(self,t=self.tspan[-1],increment=self.tspan[-1]-self.tspan[-2],seed=seed,number_of_trajectories=number_of_trajectories, stochkit_home=stochkit_home, debug=debug, show_labels=show_labels)


class Species():
    """ Chemical species. """
    
    def __init__(self,name="",initial_value=0):
        # A species has a name (string) and an initial value (positive integer)
        self.name = name
        self.initial_value = initial_value
        assert self.initial_value >= 0, "A species initial value has to \
                                        be a positive number."


class Parameter():
    """ 
        A parameter can be given as an expression (function) or directly 
        as a value (scalar). If given an expression, it should be 
        understood as evaluable in the namespace of a parent Model.
    """

    def __init__(self,name="",expression=None,value=None):

        self.name = name        
        # We allow expression to be passed in as a non-string type. Invalid strings
        # will be caught below. It is perfectly fine to give a scalar value as the expression.
        # This can then be evaluated in an empty namespace to the scalar value.
        self.expression = expression
        if expression != None:
            self.expression = str(expression)
        
        self.value = value
            
        # self.value is allowed to be None, but not self.expression. self.value
        # might not be evaluable in the namespace of this parameter, but defined
        # in the context of a model or reaction.
        if self.expression == None:
            raise TypeError
    
        if self.value == None:
            self.evaluate()
    
    def evaluate(self,namespace={}):
        """ Evaluate the expression and return the (scalar) value """
        try:
            self.value = (float(eval(self.expression, namespace)))
        except:
            self.value = None
            
    def set_expression(self,expression):
        self.expression = expression
        # We allow expression to be passed in as a non-string type. Invalid
        # strings will be caught below. It is perfectly fine to give a scalar 
        # value as the expression. This can then be evaluated in an empty 
        # namespace to the scalar value.
        if expression != None:
            self.expression = str(expression)
                    
        if self.expression == None:
            raise TypeError
    
        self.evaluate()

class Reaction():
    """ 
    Models a single reaction. A reaction has its own dictinaries of species 
    (reactants and products) and parameters. The reaction's propensity 
    function needs to be evaluable (and result in a non-negative scalar 
    value) in the namespace defined by the union of those dicts.
    """

    def __init__(self, name = "", reactants = {}, products = {}, 
                 propensity_function = None, massaction = False, 
                 rate=None, annotation=None):
        """ 
        Initializes the reaction using short-hand notation. 
        
        Input: name: string that the model is referenced by 
        parameters: a list of parameter instances 
        propensity_function: string with the expression for the reaction's 
                                propensity
        reactants: List of (species,stoiciometry)
        tuples product: List of (species,stoiciometry) 
        tuples annotation: Description of the reaction (meta)
        
            massaction True,{False}     is the reaction of mass action type
            or not?  rate                        if mass action, rate is a
            paramter instance.
        
        Raises: ReactionError
            
        """
            
        # Metadata
        self.name = name
        self.annotation = ""
        
        if rate is None and propensity_function is None:
            raise ReactionError("You must specify either a mass-action rate or a propensity function")

        # We might use this flag in the future to automatically generate
        # the propensity function if set to True.
        if propensity_function is not None:
            self.massaction = False
        else:
            self.massaction = True


        self.propensity_function = propensity_function
        if self.propensity_function is not None and self.massaction:
            errmsg = "Reaction "+self.name +" You cannot set the propensity type to mass-action and simultaneously set a propensity function."
            raise ReactionError(errmsg)
        
        self.reactants = {}
        for r in reactants:
            rtype = type(r).__name__
            if rtype=='instance':
                self.reactants[r.name] = reactants[r]
            else:
                self.reactants[r]=reactants[r]
    
        self.products = {}
        for p in products:
            rtype = type(p).__name__
            if rtype=='instance':
                self.products[p.name] = products[p]
            else:
                self.products[p]=products[p]

        if self.massaction:
            self.type = "mass-action"
            if rate is None:
                raise ReactionError("Reaction : A mass-action propensity has\
                 to have a rate.")
            self.marate = rate
            self.create_mass_action()
        else:
            self.type = "customized"
                
    def create_mass_action(self):
        """ 
            Create a mass action propensity function given
            self.reactants and a single parameter value.
        """
        # We support zeroth, first and second order propensities only.
        # There is no theoretical justification for higher order propensities.
        # Users can still create such propensities if they really want to,
        # but should then use a custom propensity.
        total_stoch=0
        for r in self.reactants:
            total_stoch+=self.reactants[r]
        if total_stoch>2:
            raise ReactionError("Reaction: A mass-action reaction cannot \
            involve more than two of one species or one of two species.")
        # Case EmptySet -> Y
        propensity_function = self.marate.name;
             
        # There are only three ways to get 'total_stoch==2':
        for r in self.reactants:
            # Case 1: 2X -> Y
            if self.reactants[r] == 2:
                propensity_function = ("0.5*" +propensity_function+ 
                                            "*"+r+"*("+r+"-1)/vol")
            else:
            # Case 3: X1, X2 -> Y;
                propensity_function += "*"+r

        # Set the volume dependency based on order.
        order = len(self.reactants)
        if order == 2:
            propensity_function += "/vol"
        elif order == 0:
            propensity_function += "*vol"

        self.propensity_function = propensity_function
            
    def setType(self,type):
        if type.lower() not in {'mass-action','customized'}:
            raise ReactionError("Invalid reaction type.")
        self.type = type.lower()

        self.massaction = False if self.type == 'customized' else True
    
    def addReactant(self,S,stoichiometry):
        if stoichiometry <= 0:
            raise ReactionError("Reaction Stoichiometry must be a \
                                    positive integer.")
        self.reactants[S.name]=stoichiometry

    def addProduct(self,S,stoichiometry):
        self.products[S.name]=stoichiometry

    def Annotate(self,annotation):
        self.annotation = annotation



# Module exceptions
class ModelError(Exception):
    pass
class SpeciesError(ModelError):
    pass
class ReactionError(ModelError):
    pass
class ParameterError(ModelError):
    pass
class SimuliationError(Exception):
    pass


class StochMLDocument():
    """ Serializiation and deserialization of a Model to/from
        the native StochKit2 XML format. """
    
    def __init__(self):
        # The root element
        self.document = etree.Element("Model")
        self.annotation = None
    
    @classmethod
    def from_model(cls,model):
        """ Creates an StochKit XML document from an exisiting Mdoel object.
            This method assumes that all the parameters in the model are already resolved
            to scalar floats (see Model.resolveParamters). 
                
            Note, this method is intended to be used interanally by the models 'serialization' 
            function, which performs additional operations and tests on the model prior to 
            writing out the XML file. You should NOT do 
            
            document = StochMLDocument.fromModel(model)
            print document.toString()
            
            you SHOULD do
            
            print model.serialize()            
            
        """
        
        # Description
        md = cls()
        
        d = etree.Element('Description') 

        #
        if model.units.lower() == "concentration":
            d.set('units', model.units.lower())

        d.text = model.annotation
        md.document.append(d)
        
        # Number of Reactions
        nr = etree.Element('NumberOfReactions')
        nr.text = str(len(model.listOfReactions))
        md.document.append(nr)
        
        # Number of Species
        ns = etree.Element('NumberOfSpecies')
        ns.text = str(len(model.listOfSpecies))
        md.document.append(ns)
        
        # Species
        spec = etree.Element('SpeciesList')
        for sname in model.listOfSpecies:
            spec.append(md.species_to_element(model.listOfSpecies[sname]))
        md.document.append(spec)
                
        # Parameters
        params = etree.Element('ParametersList')
        for pname in model.listOfParameters:
            params.append(md.parameter_to_element(
                                        model.listOfParameters[pname]))

        params.append(md.parameter_to_element(Parameter(name='vol', expression=model.volume)))

        md.document.append(params)
        
        # Reactions
        reacs = etree.Element('ReactionsList')
        for rname in model.listOfReactions:
            reacs.append(md.reaction_to_element(model.listOfReactions[rname], model.volume))
        md.document.append(reacs)
        
        return md
    
    
    @classmethod
    def from_file(cls,filepath):
        """ Intializes the document from an exisiting native StochKit XML 
        file read from disk. """
        tree = etree.parse(filepath)
        root = tree.getroot()
        md = cls()
        md.document = root
        return md

    @classmethod
    def from_string(cls,string):
        """ Intializes the document from an exisiting native StochKit XML 
        file read from disk. """
        root = etree.fromString(string)
        
        md = cls()
        md.document = root
        return md

    def to_model(self,name):
        """ Instantiates a Model object from a StochMLDocument. """
        
        # Empty model
        model = Model(name=name)
        root = self.document
        
        # Try to set name from document
        if model.name is "":
            name = root.find('Name')
            if name.text is None:
                raise
            else:
                model.name = name.text
        
        # Set annotiation
        ann = root.find('Description')
        if ann is not None:
            units = ann.get('units')

            if units:
                units = units.strip().lower()

            if units == "concentration":
                model.units = "concentration"
            elif units == "population":
                model.units = "population"
            else: # Default 
                model.units = "population"

            if ann.text is None:
                model.annotation = ""
            else:
                model.annotation = ann.text

        # Set units
        units = root.find('Units')
        if units is not None:
            if units.text.strip().lower() == "concentration":
                model.units = "concentration"
            elif units.text.strip().lower() == "population":
                model.units = "population"
            else: # Default 
                model.units = "population"
    
        # Create parameters
        for px in root.iter('Parameter'):
            name = px.find('Id').text
            expr = px.find('Expression').text
            if name.lower() == 'volume':
                model.volume = expr
            else:
                p = Parameter(name,expression=expr)
                # Try to evaluate the expression in the empty namespace 
                # (if the expr is a scalar value)
                p.evaluate()
                model.add_parameter(p)
        
        # Create species
        for spec in root.iter('Species'):
            name = spec.find('Id').text
            val  = spec.find('InitialPopulation').text
            s = Species(name,initial_value = float(val))
            model.add_species([s])
        
        # The namespace_propensity for evaluating the propensity function 
        # for reactions must contain all the species and parameters.
        namespace_propensity = OrderedDict()
        all_species = model.get_all_species()
        all_parameters = model.get_all_parameters()
        
        for param in all_species:
            namespace_propensity[param] = all_species[param].initial_value
        
        for param in all_parameters:
            namespace_propensity[param] = all_parameters[param].value
        
        # Create reactions
        for reac in root.iter('Reaction'):
            try:
                name = reac.find('Id').text
            except:
                raise InvalidStochMLError("Reaction has no name.")
            
            reaction  = Reaction(name=name,reactants={},products={})
                
            # Type may be 'mass-action','customized'
            try:
                type = reac.find('Type').text
            except:
                raise InvalidStochMLError("No reaction type specified.")
                    
            reactants  = reac.find('Reactants')
            try:
                for ss in reactants.iter('SpeciesReference'):
                    specname = ss.get('id')
                    # The stochiometry should be an integer value, but some
                    # exising StoxhKit models have them as floats. This is 
                    # why we need the slightly odd conversion below. 
                    stoch = int(float(ss.get('stoichiometry')))
                    # Select a reference to species with name specname
                    sref = model.listOfSpecies[specname]
                    try:
                        # The sref list should only contain one element if 
                        # the XML file is valid.
                        reaction.reactants[specname] = stoch
                    except Exception,e:
                        StochMLImportError(e)
            except:
                # Yes, this is correct. 'reactants' can be None
                pass

            products  = reac.find('Products')
            try:
                for ss in products.iter('SpeciesReference'):
                    specname = ss.get('id')
                    stoch = int(float(ss.get('stoichiometry')))
                    sref = model.listOfSpecies[specname]
                    try:
                        # The sref list should only contain one element if 
                        # the XML file is valid.
                        reaction.products[specname] = stoch
                    except Exception,e:
                        raise StochMLImportError(e)
            except:
                # Yes, this is correct. 'products' can be None
                pass
                            
            if type == 'mass-action':
                reaction.massaction = True
                reaction.type = 'mass-action'
                # If it is mass-action, a parameter reference is needed.
                # This has to be a reference to a species instance. We 
                # explicitly disallow a scalar value to be passed as the 
                # parameter.  
                try:
                    ratename=reac.find('Rate').text
                    try:
                        reaction.marate = model.listOfParameters[ratename]
                    except KeyError, k:
                        # No paramter name is given. This is a valid use case 
                        # in StochKit. We generate a name for the paramter, 
                        # and create a new parameter instance. The parameter's 
                        # value should now be found in 'ratename'.
                        generated_rate_name = "Reaction_" + name + \
                                                "_rate_constant"
                        p = Parameter(name=generated_rate_name, 
                                      expression=ratename)
                        # Try to evaluate the parameter to set its value
                        p.evaluate()
                        model.add_parameter(p)
                        reaction.marate = model.listOfParameters[
                                                generated_rate_name]

                    reaction.create_mass_action()
                except Exception, e:
                    raise
            elif type == 'customized':
                try:
                    propfunc = reac.find('PropensityFunction').text
                except Exception,e:
                    raise InvalidStochMLError("Found a customized " +
                    "propensity function, but no expression was given."+e)
                reaction.propensity_function = propfunc
            else:
                raise InvalidStochMLError(
                "Unsupported or no reaction type given for reaction" + name)

            model.add_reaction(reaction)
        
        return model
    
    def to_string(self):
        """ Returns  the document as a string. """
        try:
            return etree.tostring(self.document, pretty_print=True)
        except:
            # Hack to print pretty xml without pretty-print 
            # (requires the lxml module).
            doc = etree.tostring(self.document)
            xmldoc = xml.dom.minidom.parseString(doc)
            uglyXml = xmldoc.toprettyxml(indent='  ')
            text_re = re.compile(">\n\s+([^<>\s].*?)\n\s+</", re.DOTALL)
            prettyXml = text_re.sub(">\g<1></", uglyXml)
            return prettyXml
    
    def species_to_element(self,S):
        e = etree.Element('Species')
        idElement = etree.Element('Id')
        idElement.text = S.name
        e.append(idElement)
        
        if hasattr(S, 'description'):
            descriptionElement = etree.Element('Description')
            descriptionElement.text = S.description
            e.append(descriptionElement)
        
        initialPopulationElement = etree.Element('InitialPopulation')
        initialPopulationElement.text = str(S.initial_value)
        e.append(initialPopulationElement)
        
        return e
    
    def parameter_to_element(self,P):
        e = etree.Element('Parameter')
        idElement = etree.Element('Id')
        idElement.text = P.name
        e.append(idElement)
        expressionElement = etree.Element('Expression')
        expressionElement.text = str(P.value)
        e.append(expressionElement)
        return e
    
    def reaction_to_element(self,R, model_volume):
        e = etree.Element('Reaction')
        
        idElement = etree.Element('Id')
        idElement.text = R.name
        e.append(idElement)
        
        descriptionElement = etree.Element('Description')
        descriptionElement.text = self.annotation
        e.append(descriptionElement)
        

        # StochKit2 wants a rate for mass-action propensites
        if R.massaction and model_volume == 1.0:
            rateElement = etree.Element('Rate')
            # A mass-action reactions should only have one parameter
            rateElement.text = R.marate.name
            typeElement = etree.Element('Type')
            typeElement.text = 'mass-action'
            e.append(typeElement)
            e.append(rateElement)

        else:
            typeElement = etree.Element('Type')
            typeElement.text = 'customized'
            e.append(typeElement)
            functionElement = etree.Element('PropensityFunction')
            functionElement.text = R.propensity_function
            e.append(functionElement)

        reactants = etree.Element('Reactants')

        for reactant, stoichiometry in R.reactants.items():
            srElement = etree.Element('SpeciesReference')
            srElement.set('id', reactant)
            srElement.set('stoichiometry', str(stoichiometry))
            reactants.append(srElement)

        e.append(reactants)

        products = etree.Element('Products')
        for product, stoichiometry in R.products.items():
            srElement = etree.Element('SpeciesReference')
            srElement.set('id', product)
            srElement.set('stoichiometry', str(stoichiometry))
            products.append(srElement)
        e.append(products)

        return e


class GillesPySolver():
    ''' abstract class for simulation methods '''

    def run(self, model, t=20, number_of_trajectories=1,
            increment=0.05, seed=None, stochkit_home=None, algorithm=None,
            job_id=None, extra_args='', debug=False, show_labels=False):
        """ 
        Call out and run the solver. Collect the results.
        """
        
        if algorithm is None:
            raise SimuliationError("No algorithm selected")
        
        # We write all StochKit input and output files to a temporary folder
        prefix_basedir = tempfile.mkdtemp()
        prefix_outdir = os.path.join(prefix_basedir, 'output')
        os.mkdir(os.path.join(prefix_basedir, 'output'))
        
        if job_id is None:
            job_id = str(uuid.uuid4())
        
        # Write a temporary StochKit2 input file.
        if isinstance(model, Model):
            outfile =  os.path.join(prefix_basedir, "temp_input_"+job_id+".xml")
            mfhandle = open(outfile, 'w')
            #document = StochMLDocument.from_model(model)

        # If the model is a Model instance, we serialize it to XML,
        # and if it is an XML file, we just make a copy.
        if isinstance(model, Model):
            document = model.serialize()
            mfhandle.write(document)
            mfhandle.close()
        elif isinstance(model, str):
            outfile = model

        # Assemble argument list for StochKit
        ensemblename = job_id
        
        directories = os.listdir(prefix_outdir)
        
        
        outdir = prefix_outdir+'/'+ensemblename
        

        # Algorithm, SSA or Tau-leaping?
        executable = None
        if stochkit_home is not None:
            if os.path.isfile(os.path.join(stochkit_home, algorithm)):
                executable = os.path.join(stochkit_home, algorithm)
            else:
                raise SimuliationError("stochkit executable '{0}' not found \
                stochkit_home={1}".format(algorithm, stochkit_home))
        elif os.environ.get('STOCHKIT_HOME') is not None:
            if os.path.isfile(os.path.join(os.environ.get('STOCHKIT_HOME'), 
                                           algorithm)):
                executable = os.path.join(os.environ.get('STOCHKIT_HOME'), 
                                          algorithm)
        if executable is None:
            # try to find the executable in the path
            if os.environ.get('PATH') is not None:
                for dir in os.environ.get('PATH').split(':'):
                    if os.path.isfile(os.path.join(dir, algorithm)):
                        executable = os.path.join(dir, algorithm)
                        break
        if executable is None:
            raise SimulationError("stochkit executable '{0}' not found. \
                Make sure it is your path, or set STOCHKIT_HOME envronment \
                variable'".format(algorithm))



        # Assemble the argument list
        args = ''
        args += '--model '
        args += outfile
        args += ' --out-dir '+outdir
        args += ' -t '
        args += str(t)
        if increment == None:
            increment = t/20.0
        num_output_points = str(int(float(t/increment)))
        args += ' -i ' + num_output_points
        if ensemblename in directories:
            print 'Ensemble '+ensemblename+' already existed, using --force.'
            args+=' --force'
        

        # If we are using local mode, shell out and run StochKit 
        # (SSA or Tau-leaping or ODE)
        cmd = executable+' '+args+' '+extra_args
        if debug:
            print "cmd: {0}".format(cmd)

        # Execute
        try:
            #print "CMD: {0}".format(cmd)
            handle = subprocess.Popen(cmd, stdout = subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            return_code = handle.wait()
        except OSError as e:
            raise SimuliationError("Solver execution failed: \
            {0}\n{1}".format(cmd, e))
        
        try:
            stderr = handle.stderr.read()
        except Exception as e:
            stderr = 'Error reading stderr: {0}'.format(e)
        try:
            stdout = handle.stdout.read()
        except Exception as e:
            stdout = 'Error reading stdout: {0}'.format(e)

        if return_code != 0:
            #print stdout
            #print stderr
            raise SimuliationError("Solver execution failed: \
            '{0}' output: {1}{2}".format(cmd,stdout,stderr))

        # Get data using solver specific function
        try:
            if show_labels:
                labels, trajectories = self.get_trajectories(outdir, debug=debug, show_labels=True)
            else:
                trajectories = self.get_trajectories(outdir, debug=debug, show_labels=False)
        except Exception as e:
            raise SimulationError("Error using solver.get_trajectories('{0}'): {1}".format(outdir, e))

        if len(trajectories) == 0:
            #print stdout
            #print stderr
            raise SimuliationError("Solver execution failed: \
            '{0}' output: {1}{2}".format(cmd,stdout,stderr))

        # Clean up
        if debug:
            print "prefix_basedir={0}".format(prefix_basedir)
            print "STDOUT: {0}".format(stdout)
            print "STDERR: {0}".format(stderr)
        else:
            shutil.rmtree(prefix_basedir)
        # Return data
        if show_labels:
            results2 = []
            for r in trajectories:
                ret = {}
                for n,l in enumerate(labels):
                    ret[l] = r[:,n]
                results2.append(ret)
            return results2
        else:
            return trajectories

class StochKitSolver(GillesPySolver):
    ''' Solver class to simulate Stochastically with StockKit. '''
    
    @classmethod
    def run(cls, model, t=20, number_of_trajectories=1,
            increment=0.05, seed=None, stochkit_home=None, algorithm='ssa',
            job_id=None, method=None,debug=False, show_labels=False):
    
        # all this is specific to StochKit
        if model.units == "concentration":
            raise SimuliationError("StochKit can only simulate population models, please convert to population-based model for stochastic simulation. Use solver = StochKitODESolver instead to simulate a concentration model deterministically.")

        if seed is None:
            seed = random.randint(0, 2147483647)
        # StochKit breaks for long ints
        if seed.bit_length()>=32:
            seed = seed & ((1<<32)-1)
            if seed > (1 << 31) -1:
                seed -= 1 << 32

        # Only use on processor per StochKit job.
        args = ' -p 1'
      
        # We keep all the trajectories by default.
        args += ' --keep-trajectories'
        args += ' --label'

        args += ' --seed '
        args += str(seed)
        
        realizations = number_of_trajectories
        args += ' --realizations '
        args += str(realizations)

        if method is not None:  #This only works for StochKit 2.1
            args += ' --method ' + str(method)

        
        self = StochKitSolver()
        return GillesPySolver.run(self, model,t, number_of_trajectories, increment, seed, stochkit_home, algorithm, job_id, extra_args=args, debug=debug, show_labels=show_labels)

    def get_trajectories(self, outdir, debug=False, show_labels=False):
        # Collect all the output data
        files = os.listdir(outdir + '/stats')
        trajectories = []
        files = os.listdir(outdir + '/trajectories')
        labels = []
        if show_labels:
            with open(outdir + '/trajectories/trajectory0.txt', 'r') as f:
                first_line= f.readline()
                labels = first_line.split()
        for filename in files:
            if 'trajectory' in filename:
                trajectories.append(numpy.loadtxt(outdir + '/trajectories/' + 
                                        filename, skiprows=1))
            else:
                raise SimuliationError("Couldn't identify file '{0}' found in \
                                        output folder".format(filename))
        if show_labels:
            return (labels, trajectories)
        else:
            return trajectories


class StochKitODESolver(GillesPySolver):
    ''' Solver class to simulate deterministically with StockKitODE. '''
    
    @classmethod
    def run(cls, model, t=20, number_of_trajectories=1,
            increment=0.05, seed=None, stochkit_home=None, algorithm='stochkit_ode.py',
            job_id=None, debug=False, show_labels=False):
        self = StochKitODESolver()
        return GillesPySolver.run(self,model,t, number_of_trajectories, increment, seed, stochkit_home, algorithm, job_id, debug=debug, show_labels=show_labels)

    def get_trajectories(self, outdir, debug=False, show_labels=False):
        if debug:
            print "StochKitODESolver.get_trajectories(outdir={0}".format(outdir)
        # Collect all the output data
        trajectories = []
        with open(outdir + '/output.txt') as fd:
            fd.readline()
            headers = fd.readline()
            fd.readline()
            data = []
            data.append([float(x) for x in fd.readline().split()])
            fd.readline()
            for line in fd:
                data.append([float(x) for x in line.split()])
        trajectories.append(numpy.array(data))
        if show_labels:
            return (headers.split(), trajectories)
        else:
            return trajectories


# Exceptions
class StochMLImportError(Exception):
    pass

class InvalidStochMLError(Exception):
    pass

class InvalidModelError(Exception):
    pass

class SimulationError(Exception):
    pass




    
    
    
    
    
    
    
    
    
    
    
    
    
