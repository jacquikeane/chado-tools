import unittest.mock
import gffutils
from .. import dbutils, utils
from ..io import essentials, gff
from ..orm import base, general, cv, organism, pub, sequence


class TestGFF(unittest.TestCase):
    """Tests various functions used to load a GFF file into a database"""

    connection_parameters = utils.parse_yaml(dbutils.default_configuration_file())
    connection_uri = dbutils.random_database_uri(connection_parameters)

    @classmethod
    def setUpClass(cls):
        # Creates a database, establishes a connection, creates tables and populates them with essential entries
        dbutils.create_database(cls.connection_uri)
        schema_base = base.PublicBase
        schema_metadata = schema_base.metadata
        essentials_client = essentials.EssentialsClient(cls.connection_uri)
        schema_metadata.create_all(essentials_client.engine, tables=schema_metadata.sorted_tables)
        essentials_client.load()
        essentials_client._load_further_relationship_entries()
        essentials_client._load_sequence_type_entries()
        cls.client = gff.GFFImportClient(cls.connection_uri)

    @classmethod
    def tearDownClass(cls):
        # Drops the database
        dbutils.drop_database(cls.connection_uri, True)

    def setUp(self):
        # Inserts default entries into database tables
        self.default_gff_entry = gffutils.Feature(
            id="testid", seqid="testseqid", source="testsource", featuretype="testtype", start=1, end=30, score="3.5",
            strand="+", frame="2", attributes={
                "Name": ["testname"], "translation": ["MCRA"], "literature": ["PMID:12334"], "Alias": ["testalias"],
                "previous_systematic_id": "testsynonym", "Parent": "testparent", "Dbxref": ["testdb:testaccession"],
                "Ontology_term": ["GO:7890"], "Note": "testnote"})

    def tearDown(self):
        # Rolls back all changes to the database
        self.client.session.rollback()

    def insert_default_entries(self):
        # Inserts CV terms needed as basis for virtually all tests
        default_db = general.Db(name="defaultdb")
        self.client.add_and_flush(default_db)
        default_dbxref = general.DbxRef(db_id=default_db.db_id, accession="defaultaccession")
        self.client.add_and_flush(default_dbxref)
        default_cv = cv.Cv(name="defaultcv")
        self.client.add_and_flush(default_cv)
        default_cvterm = cv.CvTerm(cv_id=default_cv.cv_id, dbxref_id=default_dbxref.dbxref_id, name="testterm")
        self.client.add_and_flush(default_cvterm)
        return default_db, default_dbxref, default_cv, default_cvterm

    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_feature")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient._create_feature")
    def test_handle_child_feature(self, mock_create: unittest.mock.Mock, mock_insert: unittest.mock.Mock):
        # Tests the function transferring data from a GFF file entry to the 'feature' table
        self.assertIs(mock_create, self.client._create_feature)
        self.assertIs(mock_insert, self.client._handle_feature)
        organism_entry = organism.Organism(genus="", species="", abbreviation="testorganism", organism_id=1)
        feature_entry = self.client._handle_child_feature(self.default_gff_entry, organism_entry)
        self.assertIsNone(feature_entry)
        mock_create.assert_not_called()

        self.default_gff_entry.featuretype = "gene"
        mock_create.return_value = "AAA"
        self.client._handle_child_feature(self.default_gff_entry, organism_entry)
        mock_create.assert_called_with(self.default_gff_entry, 1, self.client._sequence_terms["gene"].cvterm_id)
        mock_insert.assert_called_with("AAA", "testorganism")

    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_featureloc")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient._create_featureloc")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient.query_first")
    def test_handle_location(self, mock_query: unittest.mock.Mock, mock_create: unittest.mock.Mock,
                             mock_insert: unittest.mock.Mock):
        # Tests the function transferring data from a GFF file entry to the 'feature' table
        self.assertIs(mock_query, self.client.query_first)
        self.assertIs(mock_create, self.client._create_featureloc)
        self.assertIs(mock_insert, self.client._handle_featureloc)

        feature_entry = sequence.Feature(organism_id=11, type_id=200, uniquename="testname", feature_id=1)
        mock_query.return_value = sequence.Feature(organism_id=11, type_id=300, uniquename="chromname", feature_id=2)

        featureloc_entry = self.client._handle_location(self.default_gff_entry, feature_entry)
        mock_query.assert_called_with(sequence.Feature, organism_id=11, uniquename="testseqid")
        mock_create.assert_called_with(self.default_gff_entry, 1, 2)
        mock_insert.assert_called()
        self.assertIsNotNone(featureloc_entry)

        mock_query.return_value = None
        featureloc_entry = self.client._handle_location(self.default_gff_entry, feature_entry)
        self.assertIsNone(featureloc_entry)

    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_feature_synonym")
    @unittest.mock.patch("pychado.orm.sequence.FeatureSynonym")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_synonym")
    @unittest.mock.patch("pychado.orm.sequence.Synonym")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient.query_all")
    def test_handle_synonyms(self, mock_query: unittest.mock.Mock, mock_synonym: unittest.mock.Mock,
                             mock_insert_synonym: unittest.mock.Mock, mock_feature_synonym: unittest.mock.Mock,
                             mock_insert_feature_synonym: unittest.mock.Mock):
        # Tests the function transferring data from a GFF file entry to the 'feature_synonym' table
        self.assertIs(mock_query, self.client.query_all)
        self.assertIs(mock_synonym, sequence.Synonym)
        self.assertIs(mock_insert_synonym, self.client._handle_synonym)
        self.assertIs(mock_feature_synonym, sequence.FeatureSynonym)
        self.assertIs(mock_insert_feature_synonym, self.client._handle_feature_synonym)

        feature_entry = sequence.Feature(organism_id=11, type_id=200, uniquename="testname", feature_id=1)
        mock_insert_synonym.return_value = utils.EmptyObject(synonym_id=12)

        all_synonyms = self.client._handle_synonyms(self.default_gff_entry, feature_entry)
        mock_query.assert_called_with(sequence.FeatureSynonym, feature_id=1)
        mock_synonym.assert_any_call(name="testalias", type_id=self.client._synonym_terms["alias"].cvterm_id,
                                     synonym_sgml="testalias")
        self.assertEqual(mock_insert_synonym.call_count, 2)
        mock_feature_synonym.assert_any_call(synonym_id=12, feature_id=1, pub_id=self.client._default_pub.pub_id,
                                             is_current=True)
        mock_feature_synonym.assert_any_call(synonym_id=12, feature_id=1, pub_id=self.client._default_pub.pub_id,
                                             is_current=False)
        self.assertEqual(mock_insert_feature_synonym.call_count, 2)
        self.assertEqual(len(all_synonyms), 2)

    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_feature_pub")
    @unittest.mock.patch("pychado.orm.sequence.FeaturePub")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_pub")
    @unittest.mock.patch("pychado.orm.pub.Pub")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient.query_all")
    def test_handle_publications(self, mock_query: unittest.mock.Mock, mock_pub: unittest.mock.Mock,
                                 mock_insert_pub: unittest.mock.Mock, mock_featurepub: unittest.mock.Mock,
                                 mock_insert_featurepub: unittest.mock.Mock):
        # Tests the function transferring data from a GFF file entry to the 'feature_pub' table
        self.assertIs(mock_query, self.client.query_all)
        self.assertIs(mock_pub, pub.Pub)
        self.assertIs(mock_insert_pub, self.client._handle_pub)
        self.assertIs(mock_featurepub, sequence.FeaturePub)
        self.assertIs(mock_insert_featurepub, self.client._handle_feature_pub)

        feature_entry = sequence.Feature(organism_id=11, type_id=200, uniquename="testname", feature_id=12)
        mock_insert_pub.return_value = utils.EmptyObject(pub_id=32, uniquename="")

        all_pubs = self.client._handle_publications(self.default_gff_entry, feature_entry)
        mock_query.assert_called_with(sequence.FeaturePub, feature_id=12)
        mock_pub.assert_any_call(uniquename="PMID:12334", type_id=self.client._default_pub.type_id)
        self.assertEqual(mock_insert_pub.call_count, 1)
        mock_featurepub.assert_any_call(feature_id=12, pub_id=32)
        self.assertEqual(mock_insert_featurepub.call_count, 1)
        self.assertEqual(len(all_pubs), 1)

    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_feature_relationship")
    @unittest.mock.patch("pychado.orm.sequence.FeatureRelationship")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient.query_all")
    def test_handle_relationships(self, mock_query: unittest.mock.Mock, mock_relationship: unittest.mock.Mock,
                                  mock_insert_relationship: unittest.mock.Mock):
        # Tests the function transferring data from a GFF file entry to the 'feature_relationship' table
        self.assertIs(mock_query, self.client.query_all)
        self.assertIs(mock_relationship, sequence.FeatureRelationship)
        self.assertIs(mock_insert_relationship, self.client._handle_feature_relationship)

        subject_entry = sequence.Feature(organism_id=11, type_id=300, uniquename="testid", feature_id=33)
        object_entry = sequence.Feature(organism_id=11, type_id=400, uniquename="testparent", feature_id=44)
        all_features = {subject_entry.uniquename: subject_entry, object_entry.uniquename: object_entry}

        all_relationships = self.client._handle_relationships(self.default_gff_entry, all_features)
        mock_query.assert_called_with(sequence.FeatureRelationship, subject_id=33)
        mock_relationship.assert_any_call(subject_id=33, object_id=44,
                                          type_id=self.client._relationship_terms["part_of"].cvterm_id)
        self.assertEqual(mock_insert_relationship.call_count, 1)
        self.assertEqual(len(all_relationships), 1)

    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_featureprop")
    @unittest.mock.patch("pychado.orm.sequence.FeatureProp")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient.query_all")
    def test_handle_properties(self, mock_query: unittest.mock.Mock, mock_prop: unittest.mock.Mock,
                               mock_insert_prop: unittest.mock.Mock):
        # Tests the function transferring data from a GFF file entry to the 'featureprop' table
        self.assertIs(mock_query, self.client.query_all)
        self.assertIs(mock_prop, sequence.FeatureProp)
        self.assertIs(mock_insert_prop, self.client._handle_featureprop)

        feature_entry = sequence.Feature(organism_id=11, type_id=200, uniquename="testname", feature_id=12)
        all_properties = self.client._handle_properties(self.default_gff_entry, feature_entry)
        mock_query.assert_called_with(sequence.FeatureProp, feature_id=12)
        mock_prop.assert_any_call(feature_id=12, type_id=self.client._feature_property_terms["source"].cvterm_id,
                                  value="testsource")
        mock_prop.assert_any_call(feature_id=12, type_id=self.client._feature_property_terms["comment"].cvterm_id,
                                  value="testnote")
        mock_prop.assert_any_call(feature_id=12, type_id=self.client._feature_property_terms["score"].cvterm_id,
                                  value="3.5")
        self.assertEqual(mock_insert_prop.call_count, 3)
        self.assertEqual(len(all_properties), 3)

    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_feature_dbxref")
    @unittest.mock.patch("pychado.orm.sequence.FeatureDbxRef")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_dbxref")
    @unittest.mock.patch("pychado.orm.general.DbxRef")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_db")
    @unittest.mock.patch("pychado.orm.general.Db")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient.query_all")
    def test_handle_crossrefs(self, mock_query: unittest.mock.Mock, mock_db: unittest.mock.Mock,
                              mock_insert_db: unittest.mock.Mock, mock_dbxref: unittest.mock.Mock,
                              mock_insert_dbxref: unittest.mock.Mock, mock_feature_dbxref: unittest.mock.Mock,
                              mock_insert_feature_dbxref: unittest.mock.Mock):
        # Tests the function transferring data from a GFF file entry to the 'feature_dbxref' table
        self.assertIs(mock_query, self.client.query_all)
        self.assertIs(mock_db, general.Db)
        self.assertIs(mock_insert_db, self.client._handle_db)
        self.assertIs(mock_dbxref, general.DbxRef)
        self.assertIs(mock_insert_dbxref, self.client._handle_dbxref)
        self.assertIs(mock_feature_dbxref, sequence.FeatureDbxRef)
        self.assertIs(mock_insert_feature_dbxref, self.client._handle_feature_dbxref)

        feature_entry = sequence.Feature(organism_id=11, type_id=200, uniquename="testname", feature_id=12)
        mock_insert_db.return_value = utils.EmptyObject(db_id=44, name="")
        mock_insert_dbxref.return_value = utils.EmptyObject(dbxref_id=55, accession="", version="")

        all_crossrefs = self.client._handle_cross_references(self.default_gff_entry, feature_entry)
        mock_query.assert_called_with(sequence.FeatureDbxRef, feature_id=12)
        mock_db.assert_any_call(name="testdb")
        mock_dbxref.assert_any_call(db_id=44, accession="testaccession", version="")
        mock_feature_dbxref.assert_any_call(feature_id=12, dbxref_id=55)
        self.assertEqual(mock_insert_db.call_count, 1)
        self.assertEqual(mock_insert_dbxref.call_count, 1)
        self.assertEqual(mock_insert_feature_dbxref.call_count, 1)
        self.assertEqual(len(all_crossrefs), 1)

    @unittest.mock.patch("pychado.io.gff.GFFImportClient._handle_feature_cvterm")
    @unittest.mock.patch("pychado.orm.sequence.FeatureCvTerm")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient.query_first")
    @unittest.mock.patch("pychado.io.gff.GFFImportClient.query_all")
    def test_handle_ontology_terms(self, mock_query: unittest.mock.Mock, mock_query_first: unittest.mock.Mock,
                                   mock_feature_cvterm: unittest.mock.Mock,
                                   mock_insert_feature_cvterm: unittest.mock.Mock):
        # Tests the function transferring data from a GFF file entry to the 'feature_cvterm' table
        self.assertIs(mock_query, self.client.query_all)
        self.assertIs(mock_query_first, self.client.query_first)
        self.assertIs(mock_feature_cvterm, sequence.FeatureCvTerm)
        self.assertIs(mock_insert_feature_cvterm, self.client._handle_feature_cvterm)

        feature_entry = sequence.Feature(organism_id=11, type_id=200, uniquename="testname", feature_id=12)
        mock_query_first.side_effect = [utils.EmptyObject(db_id=33),
                                        utils.EmptyObject(dbxref_id=44),
                                        utils.EmptyObject(cvterm_id=55)]

        all_ontology_terms = self.client._handle_ontology_terms(self.default_gff_entry, feature_entry)
        mock_query_first.assert_any_call(general.Db, name="GO")
        mock_query_first.assert_any_call(general.DbxRef, db_id=33, accession="7890")
        mock_query_first.assert_any_call(cv.CvTerm, dbxref_id=44)
        self.assertEqual(mock_query_first.call_count, 3)
        mock_feature_cvterm.assert_any_call(feature_id=12, cvterm_id=55, pub_id=self.client._default_pub.pub_id)
        self.assertEqual(mock_insert_feature_cvterm.call_count, 1)
        self.assertEqual(len(all_ontology_terms), 1)

    def test_create_feature(self):
        # Tests the function that creates an entry for the 'feature' table
        feature = self.client._create_feature(self.default_gff_entry, 3, 5)
        self.assertEqual(feature.organism_id, 3)
        self.assertEqual(feature.type_id, 5)
        self.assertEqual(feature.uniquename, "testid")
        self.assertEqual(feature.name, "testname")
        self.assertEqual(feature.residues, "MCRA")
        self.assertEqual(feature.seqlen, 4)

    def test_create_featureloc(self):
        # Tests the function that creates an entry for the 'featureloc' table
        featureloc = self.client._create_featureloc(self.default_gff_entry, 3, 5)
        self.assertEqual(featureloc.feature_id, 3)
        self.assertEqual(featureloc.srcfeature_id, 5)
        self.assertEqual(featureloc.fmin, 0)
        self.assertEqual(featureloc.fmax, 30)
        self.assertEqual(featureloc.strand, 1)
        self.assertEqual(featureloc.phase, 2)

    def test_extract_name(self):
        # Tests the function that extracts the name from a GFF file entry
        feature = gffutils.Feature()
        name = self.client._extract_name(feature)
        self.assertIsNone(name)
        feature.attributes = {"Name": "testname"}
        name = self.client._extract_name(feature)
        self.assertEqual(name, "testname")
        feature.attributes = {"Name": ["othername"]}
        name = self.client._extract_name(feature)
        self.assertEqual(name, "othername")

    def test_extract_synonyms(self):
        # Tests the function that extracts the synonyms from a GFF file entry
        feature = gffutils.Feature(attributes={"Alias": "testalias", "previous_systematic_id": ["testsynonym"]})
        synonyms = self.client._extract_synonyms(feature)
        self.assertEqual(len(synonyms), 2)
        self.assertEqual(synonyms["alias"], ["testalias"])
        self.assertEqual(synonyms["previous_systematic_id"], ["testsynonym"])

    def test_extract_residues(self):
        # Tests the function that extracts an amino acid sequence from a GFF file entry
        feature = gffutils.Feature()
        residues = self.client._extract_residues(feature)
        self.assertIsNone(residues)
        feature.attributes = {"translation": "actgaa"}
        residues = self.client._extract_residues(feature)
        self.assertEqual(residues, "ACTGAA")
        feature.attributes = {"translation": ["cTTg"]}
        residues = self.client._extract_residues(feature)
        self.assertEqual(residues, "CTTG")

    def test_extract_relationships(self):
        # Tests the function that extracts feature relationships from a GFF file entry
        feature = gffutils.Feature(attributes={"Parent": "parentterm", "Derives_from": ["otherterm"],
                                               "other_key": "other_value"})
        relationships = self.client._extract_relationships(feature)
        self.assertEqual(len(relationships), 2)
        self.assertEqual(relationships["part_of"], ["parentterm"])
        self.assertEqual(relationships["derives_from"], ["otherterm"])

    def test_extract_properties(self):
        # Tests the function that extracts feature properties from a GFF file entry
        feature = gffutils.Feature(source="testsource", score="2.54",
                                   attributes={"Parent": "parentterm", "comment": ["first_value", "second_value"]})
        properties = self.client._extract_properties(feature)
        self.assertEqual(len(properties), 3)
        self.assertEqual(properties["source"], ["testsource"])
        self.assertEqual(properties["score"], ["2.54"])
        self.assertEqual(properties["comment"], ["first_value", "second_value"])

    def test_extract_crossrefs(self):
        # Tests the function that extracts database cross references from a GFF file entry
        feature = gffutils.Feature(attributes={"Dbxref": "Wikipedia:gene", "Ontology_term": ["GO:12345", "GO:67890"]})
        crossrefs = self.client._extract_crossrefs(feature)
        self.assertEqual(len(crossrefs), 1)
        self.assertIn("Wikipedia:gene", crossrefs)

    def test_extract_ontology_terms(self):
        # Tests the function that extracts ontology terms from a GFF file entry
        feature = gffutils.Feature(attributes={"Dbxref": "Wikipedia:gene", "Ontology_term": ["GO:12345", "GO:67890"]})
        ontology_terms = self.client._extract_ontology_terms(feature)
        self.assertEqual(len(ontology_terms), 2)
        self.assertIn("GO:67890", ontology_terms)

    def test_extract_publications(self):
        # Tests the function that extracts publications from a GFF file entry
        feature = gffutils.Feature(attributes={"literature": "PMID:12345"})
        publications = self.client._extract_publications(feature)
        self.assertEqual(len(publications), 1)
        self.assertIn("PMID:12345", publications)

    def test_convert_strand(self):
        # Tests the function converting the 'strand' attribute from string notation to integer notation
        gff_strand = "+"
        chado_strand = gff.convert_strand(gff_strand)
        self.assertEqual(chado_strand, 1)
        gff_strand = "-"
        chado_strand = gff.convert_strand(gff_strand)
        self.assertEqual(chado_strand, -1)
        gff_strand = "something_elsa"
        chado_strand = gff.convert_strand(gff_strand)
        self.assertIsNone(chado_strand)

    def test_convert_frame(self):
        # Tests the function converting the 'frame' attribute from string notation to integer notation
        gff_frame = "."
        chado_frame = gff.convert_frame(gff_frame)
        self.assertIsNone(chado_frame)
        gff_frame = "2"
        chado_frame = gff.convert_frame(gff_frame)
        self.assertEqual(chado_frame, 2)
        gff_frame = "3"
        chado_frame = gff.convert_frame(gff_frame)
        self.assertIsNone(chado_frame)


if __name__ == '__main__':
    unittest.main(verbosity=2, buffer=True)
