import pytest

import os
import json
import pandas as pd

from mag_annotator.utils import run_process, make_mmseqs_db, merge_files, multigrep, remove_prefix, remove_suffix, \
    get_ids_from_row
from mag_annotator.pull_sequences import get_genes_from_identifiers


def test_run_process():
    run_process(['echo', 'Hello', 'World'], verbose=True)


@pytest.fixture()
def mmseqs_db_dir(tmpdir):
    return tmpdir.mkdir('make_mmseqs_db_test')


@pytest.fixture()
def test_make_mmseqs_db(mmseqs_db_dir):
    faa_path = os.path.join('tests', 'data', 'NC_001422.faa')
    output_file = str(mmseqs_db_dir.join('mmseqs_db.mmsdb'))
    make_mmseqs_db(faa_path, output_file, True, 1)
    assert os.path.isfile(output_file)


@pytest.fixture()
def merge_test_dir(tmpdir):
    return tmpdir.mkdir('test_merge')


@pytest.fixture()
def files_to_merge_no_header(merge_test_dir):
    files_to_merge = []
    for i in range(3):
        merge_file = merge_test_dir.join(f'merge_test.{str(i)}.txt')
        merge_file.write('test%s\n' % str(i))
        files_to_merge.append(merge_file)
    return files_to_merge


@pytest.fixture()
def files_to_merge_w_header(merge_test_dir):
    files_to_merge = []
    header = 'gene_name'
    for i in range(3):
        merge_file = merge_test_dir.join(f'merge_test_w_header.{str(i)}.txt')
        merge_file.write('%s\ntest%s\n' % (header, str(i)))
        files_to_merge.append(merge_file)
    return files_to_merge


def test_merge_files(files_to_merge_no_header, files_to_merge_w_header, merge_test_dir):
    test_merge = merge_test_dir.join('merged_test.txt')
    merge_files(files_to_merge_no_header, test_merge, False)
    assert len(test_merge.readlines()) == 3

    test_merge_w_header = merge_test_dir.join('merged_test_w_header.txt')
    merge_files(files_to_merge_w_header, test_merge_w_header, True)
    assert len(test_merge_w_header.readlines()) == 4


@pytest.fixture()
def multigrep_inputs(tmpdir):
    hits = ['gene1', 'gene3', 'gene5']
    data_str = "gene1 something about gene1\n" \
               "gene2 gene2 information\n" \
               "gene3 data including gene3\n" \
               "gene4 data including gene4\n" \
               "gene5 data including gene5\n"
    data_file = tmpdir.mkdir('multigrep_test').join('multigrep_test_data.txt')
    data_file.write(data_str)
    return hits, str(data_file)


def test_multigrep(multigrep_inputs):
    keys, values = multigrep_inputs
    dict_ = multigrep(keys, values)
    assert len(dict_) == len(keys)
    assert dict_['gene1'] == 'gene1 something about gene1'
    assert dict_['gene3'] == 'gene3 data including gene3'
    assert dict_['gene5'] == 'gene5 data including gene5'


def test_remove_prefix():
    assert remove_prefix('prefix', 'pre') == 'fix'
    assert remove_prefix('postfix', 'pre') == 'postfix'


def test_remove_suffix():
    assert remove_suffix('suffix', 'fix') == 'suf'
    assert remove_suffix('postfix', 'suf') == 'postfix'


def test_get_ids_from_row():
    id_set1 = get_ids_from_row(pd.Series({'ko_id': 'K00001,K00003'}))
    assert id_set1 == {'K00001', 'K00003'}
    id_set2 = get_ids_from_row(pd.Series({'kegg_hit': 'Some text and then [EC:0.0.0.0]; also [EC:1.1.1.1]'}))
    assert id_set2 == {'EC:0.0.0.0', 'EC:1.1.1.1'}
    id_set3 = get_ids_from_row(pd.Series({'peptidase_family': 'ABC1;BCD2'}))
    assert id_set3 == {'ABC1', 'BCD2'}
    id_set4 = get_ids_from_row(pd.Series({'cazy_hits': 'GH4 some things [GH4]; GT6 other things [GT6]'}))
    assert id_set4 == {'GH4', 'GT6'}


@pytest.fixture()
def annotations():
    return pd.DataFrame([['bin.1', 'scaffold_1', None],
                         ['bin.1', 'scaffold_1', 'K00001'],
                         ['bin.1', 'scaffold_1', 'K00016'],
                         ['bin.1', 'scaffold_1', None],
                         ['bin.1', 'scaffold_2', None],
                         ['bin.2', 'scaffold_1', None],
                         ['bin.2', 'scaffold_1', None],
                         ['bin.2', 'scaffold_1', 'K00001,K13954']],
                        index=['gene1', 'gene2', 'gene3', 'gene4', 'gene5', 'gene6', 'gene7', 'gene8'],
                        columns=['fasta', 'scaffold', 'ko_id'])


def test_get_genes_from_identifiers(annotations):
    # filter by genes
    genes_to_keep = ['gene1', 'gene4', 'gene8']
    kept_genes = get_genes_from_identifiers(annotations, genes=genes_to_keep)
    assert set(kept_genes) == set(genes_to_keep)
    # filter by scaffolds
    scaffolds_to_keep = ['scaffold_2']
    kept_genes = get_genes_from_identifiers(annotations, scaffolds=scaffolds_to_keep)
    assert set(kept_genes) == {'gene5'}
    # filter by bin
    bins_to_keep = ['bin.2']
    kept_genes = get_genes_from_identifiers(annotations, fastas=bins_to_keep)
    assert set(kept_genes) == {'gene6', 'gene7', 'gene8'}
    # filter by bin and scaffold
    kept_genes = get_genes_from_identifiers(annotations, fastas=['bin.2'], scaffolds=['scaffold_2'])
    assert set(kept_genes) == {'gene5', 'gene6', 'gene7', 'gene8'}
    # filter by ko
    kept_genes = get_genes_from_identifiers(annotations, identifiers=['K00001'])
    assert set(kept_genes) == {'gene2', 'gene8'}
    # filter by bin and ko
    kept_genes = get_genes_from_identifiers(annotations, fastas=['bin.1'], identifiers=['K00001'])
    assert set(kept_genes) == {'gene2'}

# def test_get_gene_neighborhood
#     # test distance in bp works
#
#     # test distance in genes works
#
#     # test distances work together
