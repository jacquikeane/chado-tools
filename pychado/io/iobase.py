from typing import List, Dict
import sqlalchemy.orm
from .. import utils, ddl
from ..orm import general, cv, pub, organism, sequence


class DatabaseError(Exception):
    pass


class InputFileError(Exception):
    pass


class IOClient(ddl.ChadoClient):
    """Base class for read-write access to a CHADO database"""

    def __init__(self, uri: str):
        """Constructor - connect to database"""
        super().__init__(uri)
        session_maker = sqlalchemy.orm.sessionmaker(bind=self.engine)
        self.session = session_maker()                                              # type: sqlalchemy.orm.Session

    def __del__(self):
        """Destructor - disconnect from database"""
        self.session.close()
        super().__del__()

    def query_table(self, table, **kwargs) -> sqlalchemy.orm.Query:
        """Creates a query on a database table from given keyword arguments"""
        query = self.session.query(table)
        if kwargs:
            query = query.filter_by(**kwargs)
        return query

    def query_all(self, table, **kwargs):
        """Helper class querying a table and returning all results"""
        return self.query_table(table, **kwargs).all()

    def query_first(self, table, **kwargs):
        """Helper class querying a table and returning the first result"""
        return self.query_table(table, **kwargs).first()

    def add_and_flush(self, obj):
        """Adds an entry to a database table"""
        self.session.add(obj)
        self.session.flush()

    def insert_into_table(self, table, **kwargs):
        """Creates an entry and inserts it into a database table"""
        obj = table(**kwargs)
        self.add_and_flush(obj)
        return obj

    def find_or_insert(self, table, **kwargs):
        """Returns one entry of a database table matching a query. If no matching entry exists, it is created."""
        entry = self.query_first(table, **kwargs)
        if not entry:
            entry = self.insert_into_table(table, **kwargs)
        return entry


class ImportClient(IOClient):
    """Base class for importing data into a CHADO database"""
    
    def __init__(self, uri: str, verbose=False):
        """Constructor"""

        # Connect to database
        super().__init__(uri)

        # Set up printer
        self.printer = utils.VerbosePrinter(verbose)
        
    def _load_cvterm(self, term: str) -> cv.CvTerm:
        """Loads a specific CV term"""
        cvterm_entry = self.query_first(cv.CvTerm, name=term)
        if not cvterm_entry:
            raise DatabaseError("CV term '" + term + "' not present in database")
        return cvterm_entry

    def _load_cvterms(self, vocabulary: str, terms: List[str], relationship=False) -> Dict[str, cv.CvTerm]:
        """Loads CV terms from a given vocabulary and returns them in a dictionary, keyed by name"""
        cv_entry = self.query_first(cv.Cv, name=vocabulary)
        if not cv_entry:
            raise DatabaseError("CV '" + vocabulary + "' not present in database")
        cvterm_entries = self.query_all(cv.CvTerm, cv_id=cv_entry.cv_id, is_relationshiptype=int(relationship))
        cvterm_entries_dict = utils.list_to_dict(cvterm_entries, "name")
        for term in terms:
            if term not in cvterm_entries_dict:
                raise DatabaseError("CV term '" + term + "' not present in database")
        return cvterm_entries_dict

    def _load_pub(self, pub_name: str) -> pub.Pub:
        """Loads a pub entry from the database"""
        pub_entry = self.query_first(pub.Pub, uniquename=pub_name)
        if not pub_entry:
            raise DatabaseError("Pub '" + pub_name + "' not present in database")
        return pub_entry

    def _load_organism(self, organism_name: str) -> organism.Organism:
        """Loads an organism entry from the database"""
        organism_entry = self.query_first(organism.Organism, abbreviation=organism_name)
        if not organism_entry:
            raise DatabaseError("Organism '" + organism_name + "' not present in database")
        return organism_entry

    def _handle_db(self, new_entry: general.Db) -> general.Db:
        """Inserts or updates an entry in the 'db' table, and returns it"""

        # Check if the db is already present in the database
        existing_entry = self.query_first(general.Db, name=new_entry.name)
        if existing_entry:

            # Nothing to update, return existing entry
            return existing_entry
        else:

            # Insert new db entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted db '" + new_entry.name + "'")
            return new_entry

    def _handle_dbxref(self, new_entry: general.DbxRef, db_authority="") -> general.DbxRef:
        """Inserts or updates an entry in the 'dbxref' table, and returns it"""

        # Check if the dbxref is already present in the database
        existing_entry = self.query_first(general.DbxRef, db_id=new_entry.db_id, accession=new_entry.accession)
        if existing_entry:

            # Nothing to update, return existing entry
            return existing_entry
        else:

            # Insert new db entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted dbxref '" + db_authority + "." + new_entry.accession + "'")
            return new_entry

    def _handle_cv(self, new_entry: cv.Cv) -> cv.Cv:
        """Inserts or updates an entry in the 'cv' table, and returns it"""

        # Check if the cv is already present in the database
        existing_entry = self.query_first(cv.Cv, name=new_entry.name)
        if existing_entry:

            # Nothing to update, return existing entry
            return existing_entry
        else:

            # Insert new cv entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted controlled vocabulary '" + new_entry.name + "'")
            return new_entry

    def _handle_cvterm(self, new_entry: cv.CvTerm, vocabulary="") -> cv.CvTerm:
        """Inserts or updates an entry in the 'cvterm' table, and returns it"""

        # Check if the cvterm is already present in the database (look for dbxref)
        existing_entry = self.query_first(cv.CvTerm, dbxref_id=new_entry.dbxref_id)
        if existing_entry:

            # Nothing to update, return existing entry
            return existing_entry
        else:

            # Check if the cvterm is already present in the database (look for cv_id and name)
            existing_entry = self.query_first(cv.CvTerm, cv_id=new_entry.cv_id, name=new_entry.name)
            if existing_entry:

                # Nothing to update, return existing entry
                return existing_entry
            else:

                # Insert new cvterm entry
                self.add_and_flush(new_entry)
                self.printer.print("Inserted term '" + new_entry.name + "' in vocabulary '" + vocabulary + "'")
                return new_entry

    def _handle_feature_dbxref(self, new_entry: sequence.FeatureDbxRef, existing_entries: List[sequence.FeatureDbxRef],
                               crossref="", feature="") -> sequence.FeatureDbxRef:
        """Inserts or updates an entry in the 'feature_dbxref' table, and returns it"""

        # Check if the feature_dbxref is already present in the database
        matching_entries = utils.filter_objects(existing_entries, dbxref_id=new_entry.dbxref_id)
        if matching_entries:

            # Check if the entries in database and file have the same properties (there can only be one)
            matching_entry = matching_entries[0]
            if self.update_feature_dbxref_properties(matching_entry, new_entry):
                self.printer.print("Updated cross reference '" + crossref + "' for feature '" + feature + "'")
            return matching_entry
        else:

            # Insert new feature_dbxref entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted cross reference '" + crossref + "' for feature '" + feature + "'")
            return new_entry

    def _handle_feature(self, new_entry: sequence.Feature, organism_name="") -> sequence.Feature:
        """Inserts or updates an entry in the 'feature' table and returns it"""

        # Check if the feature is already present in the database
        existing_entry = self.query_first(sequence.Feature, organism_id=new_entry.organism_id,
                                          type_id=new_entry.type_id, uniquename=new_entry.uniquename)
        if existing_entry:

            # Check if the entries in database and file have the same properties, and update if not
            if self.update_feature_properties(existing_entry, new_entry):
                self.printer.print("Updated feature '" + existing_entry.uniquename + "' for organism '"
                                   + organism_name + "'")
            return existing_entry
        else:

            # Insert new feature entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted feature '" + new_entry.uniquename + "' for organism '" + organism_name + "'")
            return new_entry

    def _handle_featureloc(self, new_entry: sequence.FeatureLoc, feature="") -> sequence.FeatureLoc:
        """Inserts or updates an entry in the 'featureloc' table, and returns it"""

        # Check if the featureloc is already present in the database
        existing_entry = self.query_first(sequence.FeatureLoc, feature_id=new_entry.feature_id)
        if existing_entry:

            # Check if the entries in database and file have the same properties, and update if not
            if self.update_featureloc_properties(existing_entry, new_entry):
                self.printer.print("Updated featureloc for feature '" + feature + "'")
            return existing_entry
        else:

            # Insert new featureloc entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted featureloc for feature '" + feature + "'")
            return new_entry

    def _handle_featureprop(self, new_entry: sequence.FeatureProp, existing_entries: List[sequence.FeatureProp],
                            property_name="", value="", feature="") -> sequence.FeatureProp:
        """Inserts or updates an entry in the 'featureprop' table, and returns it"""

        # Check if the featureprop is already present in the database
        matching_entries = utils.filter_objects(existing_entries, type_id=new_entry.type_id)
        for matching_entry in matching_entries:

            # Check if the entries in database and file have the same properties
            if matching_entry.value == new_entry.value:

                # Nothing to update; return existing entry
                return matching_entry
            else:

                # Adjust 'rank' to avoid a violation of the UNIQUE constraint
                new_entry.rank = max(new_entry.rank, matching_entry.rank+1)
        else:

            # Insert new featureprop entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted property '" + property_name + "' = '" + value + "' for feature '"
                               + feature + "'")
            return new_entry

    def _handle_feature_cvterm(self, new_entry: sequence.FeatureCvTerm, existing_entries: List[sequence.FeatureCvTerm],
                               term="", feature="") -> sequence.FeatureCvTerm:
        """Inserts or updates an entry in the 'feature_cvterm' table, and returns it"""

        # Check if the feature_cvterm is already present in the database
        matching_entries = utils.filter_objects(existing_entries, cvterm_id=new_entry.cvterm_id)
        if matching_entries:

            # Nothing to update; return existing entry
            # Note that there are potentially multiple entries (for different pub_ids/ranks). Ignored here.
            return matching_entries[0]
        else:

            # Insert new feature_cvterm entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted CV term '" + term + "' for feature '" + feature + "'")
            return new_entry

    def _handle_feature_relationship(self, new_entry: sequence.FeatureRelationship,
                                     existing_entries: List[sequence.FeatureRelationship],
                                     subject_name="", object_name="", type_name="") -> sequence.FeatureRelationship:
        """Inserts or updates an entry in the 'feature_relationship' table, and returns it"""

        # Check if the feature_relationship is already present in the database
        matching_entries = utils.filter_objects(existing_entries, type_id=new_entry.type_id,
                                                object_id=new_entry.object_id)
        if matching_entries:

            # Check if the entries in database and file have the same properties, and update if not
            # Note that there are potentially multiple entries (for different ranks). Ignored here.
            matching_entry = matching_entries[0]
            if self.update_feature_relationship_properties(matching_entry, new_entry):
                self.printer.print("Updated relationship: '" + subject_name + "', '" + type_name + "', '"
                                   + object_name + "'")
            return matching_entry
        else:

            # Insert new feature_relationship entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted relationship: '" + subject_name + "', '" + type_name + "', '"
                               + object_name + "'")
            return new_entry

    def _handle_synonym(self, new_entry: sequence.Synonym) -> sequence.Synonym:
        """Inserts or updates an entry in the 'synonym' table, and returns it"""

        # Check if the synonym is already present in the database
        existing_entry = self.query_first(sequence.Synonym, name=new_entry.name, type_id=new_entry.type_id)
        if existing_entry:

            # Check if the entries in database and file have the same properties, and update if not
            if self.update_synonym_properties(existing_entry, new_entry):
                self.printer.print("Updated synonym '" + existing_entry.name + "'.")
            return existing_entry
        else:

            # Insert a new synonym entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted synonym '" + new_entry.name + "'.")
            return new_entry

    def _handle_feature_synonym(self, new_entry: sequence.FeatureSynonym,
                                existing_entries: List[sequence.FeatureSynonym], synonym="", feature=""
                                ) -> sequence.FeatureSynonym:
        """Inserts or updates an entry in the 'feature_synonym' table, and returns it"""

        # Check if the feature_synonym is already present in the database
        matching_entries = utils.filter_objects(existing_entries, synonym_id=new_entry.synonym_id)
        if matching_entries:

            # Check if the entries in database and file have the same properties, and update if not
            # Note that there are potentially multiple entries (for different pub_ids). Ignored here.
            matching_entry = matching_entries[0]
            if self.update_feature_synonym_properties(matching_entry, new_entry):
                self.printer.print("Updated synonym '" + synonym + "' for feature '" + feature + "'")
            return matching_entry
        else:

            # Insert a new feature_synonym entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted synonym '" + synonym + "' for feature '" + feature + "'")
            return new_entry

    def _handle_pub(self, new_entry: pub.Pub) -> pub.Pub:
        """Inserts or updates an entry in the 'pub' table, and returns it"""

        # Check if the publication is already present in the database
        existing_entry = self.query_first(pub.Pub, uniquename=new_entry.uniquename, type_id=new_entry.type_id)
        if existing_entry:

            # Check if the entries in database and file have the same properties, and update if not
            if self.update_pub_properties(existing_entry, new_entry):
                self.printer.print("Updated publication '" + new_entry.uniquename + "'")
            return existing_entry
        else:

            # Insert a new feature_synonym entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted publication '" + new_entry.uniquename + "'")
            return new_entry

    def _handle_feature_pub(self, new_entry: sequence.FeaturePub, existing_entries: List[sequence.FeaturePub],
                            feature="", publication="") -> sequence.FeaturePub:
        """Inserts or updates an entry in the 'feature_pub' table, and returns it"""

        # Check if the feature_pub is already present in the database
        matching_entries = utils.filter_objects(existing_entries, pub_id=new_entry.pub_id)
        if matching_entries:

            # Nothing to update, return existing entry
            matching_entry = matching_entries[0]
            return matching_entry
        else:

            # Insert a new feature_pub entry
            self.add_and_flush(new_entry)
            self.printer.print("Inserted publication '" + publication + "' for feature '" + feature + "'")
            return new_entry

    @staticmethod
    def update_pub_properties(existing_entry: pub.Pub, new_entry: pub.Pub) -> bool:
        """Updates the properties of a pub entry in the database"""
        updated = False
        for attribute in ["title", "volume", "volumetitle", "series_name", "issue", "pyear", "pages", "miniref",
                          "publisher", "pubplace", "is_obsolete"]:
            if utils.copy_attribute(existing_entry, new_entry, attribute):
                updated = True
        return updated

    @staticmethod
    def update_feature_properties(existing_entry: sequence.Feature, new_entry: sequence.Feature) -> bool:
        """Updates the properties of a feature entry in the database"""
        updated = False
        for attribute in ["name", "residues", "seqlen", "md5checksum", "is_analysis", "is_obsolete"]:
            if utils.copy_attribute(existing_entry, new_entry, attribute):
                updated = True
        return updated

    @staticmethod
    def update_featureloc_properties(existing_entry: sequence.FeatureLoc, new_entry: sequence.FeatureLoc) -> bool:
        """Updates the properties of a featureloc entry in the database"""
        updated = False
        for attribute in ["fmin", "fmax", "strand", "phase"]:
            if utils.copy_attribute(existing_entry, new_entry, attribute):
                updated = True
        return updated

    @staticmethod
    def update_feature_dbxref_properties(existing_entry: sequence.FeatureDbxRef,
                                         new_entry: sequence.FeatureDbxRef) -> bool:
        """Updates the properties of a feature_dbxref entry in the database"""
        updated = False
        if utils.copy_attribute(existing_entry, new_entry, "is_current"):
            updated = True
        return updated

    @staticmethod
    def update_feature_relationship_properties(existing_entry: sequence.FeatureRelationship,
                                               new_entry: sequence.FeatureRelationship) -> bool:
        """Updates the properties of a feature_relationship entry in the database"""
        updated = False
        if utils.copy_attribute(existing_entry, new_entry, "value"):
            updated = True
        return updated

    @staticmethod
    def update_synonym_properties(existing_entry: sequence.Synonym, new_entry: sequence.Synonym) -> bool:
        """Updates the properties of a synonym entry in the database"""
        updated = False
        if utils.copy_attribute(existing_entry, new_entry, "synonym_sgml"):
            updated = True
        return updated

    @staticmethod
    def update_feature_synonym_properties(existing_entry: sequence.FeatureSynonym,
                                          new_entry: sequence.FeatureSynonym) -> bool:
        """Updates the properties of a feature_synonym entry in the database"""
        updated = False
        for attribute in ["is_internal", "is_current"]:
            if utils.copy_attribute(existing_entry, new_entry, attribute):
                updated = True
        return updated
