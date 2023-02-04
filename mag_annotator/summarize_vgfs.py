import pandas as pd
import altair as alt
import re
from os import path, mkdir
from functools import partial
from collections import defaultdict, Counter
from datetime import datetime
import warnings

from mag_annotator.database_handler import DatabaseHandler
from mag_annotator.utils import get_ids_from_row, get_ids_from_annotation, get_ordered_uniques

VOGDB_TYPE_NAMES = {'Xr': 'Viral replication genes', 'Xs': 'Viral structure genes',
                    'Xh': 'Viral genes with host benefits', 'Xp': 'Viral genes with viral benefits',
                    'Xu': 'Viral genes with unknown function', 'Xx': 'Viral hypothetical genes'}
VIRUS_STATS_COLUMNS = ['VIRSorter category', 'Circular', 'Prophage', 'Gene count', 'Strand switches',
                       'potential AMG count', 'Transposase present', 'Possible Non-Viral Contig']
VIRAL_DISTILLATE_COLUMNS = ['gene', 'scaffold', 'gene_id', 'gene_description', 'category', 'header',
                            'subheader', 'module', 'auxiliary_score', 'amg_flags']
VIRAL_LIQUOR_HEADERS = ['Category', 'Function', 'AMG Genes', 'Genes Present', 'Contig Name', 'Present in Contig']
HEATMAP_CELL_HEIGHT = 10
HEATMAP_CELL_WIDTH = 10

defaultdict_list = partial(defaultdict, list)


def add_custom_ms(annotations, distillate_form):
    metabolic_genes = set(distillate_form.index)

    new_amg_flags = []
    for gene, row in annotations.iterrows():
        if 'M' in row['amg_flags']:
            new_amg_flags.append(row['amg_flags'])
        else:
            gene_annotations = set(get_ids_from_annotation(pd.DataFrame(row).transpose()).keys())
            if len(metabolic_genes & gene_annotations) > 0:
                new_amg_flags.append(row['amg_flags'] + 'M')
            else:
                new_amg_flags.append(row['amg_flags'])
    return new_amg_flags


def filter_to_amgs(annotations, max_aux=4, remove_transposons=True, remove_fs=False):
    # def filter_to_amgs(annotations, max_aux=4, remove_transposons=True, remove_fs=False, remove_js=False):
    potential_amgs = []
    for gene, row in annotations.iterrows():
        amg_flags = row['amg_flags']
        if not pd.isna(amg_flags):
            vmap_aux_check = ('V' not in amg_flags) and ('M' in amg_flags) and (row['auxiliary_score'] <= max_aux) and \
                             ('A' not in amg_flags) and ('P' not in amg_flags)
            remove_t = (remove_transposons and 'T' not in amg_flags) or not remove_transposons
            remove_f = (remove_fs and 'F' not in amg_flags) or not remove_fs
            # remove_j = (remove_fs and 'J' not in amg_flags) or not remove_js
            # if vmap_aux_check and remove_t and remove_f and remove_j:
            if vmap_aux_check and remove_t and remove_f:
                potential_amgs.append(gene)
    return annotations.loc[potential_amgs]


def get_strand_switches(strandedness):
    switches = 0
    strand = strandedness[0]
    for i in range(len(strandedness)):
        if strandedness[i] != strand:
            switches += 1
            strand = strandedness[i]
    return switches


def make_viral_stats_table(annotations, potential_amgs, groupby_column='scaffold'):
    amg_counts = potential_amgs.groupby(groupby_column).size()
    viral_stats_series = []
    for scaffold, frame in annotations.groupby(groupby_column):
        # get virus information
        virus_categories = re.findall(r'-cat_\d$', scaffold)
        if len(virus_categories) > 0:
            virus_category = int(virus_categories[0].split('_')[-1])  # viral category
            virus_prophage = virus_category in {4, 5}
        else:
            virus_category = None
            virus_prophage = None
        virus_circular = len(re.findall(r'-circular-cat_\d$', scaffold)) == 1  # virus is circular
        virus_num_genes = len(frame)  # number of genes on viral contig
        virus_strand_switches = get_strand_switches(frame.strandedness)  # number of strand switches
        virus_number_amgs = amg_counts[scaffold] if scaffold in amg_counts else 0
        virus_transposase_present = sum(frame.is_transposon) > 0  # transposase on contig
        # virus_j_present = sum(['J' in i if not pd.isna(i) else False for i in frame.amg_flags]) > 0
        virus_j_present = (
            sum(
                False if pd.isna(i) else i == 'Xh'
                for i in frame['vogdb_categories']
            )
            / frame.shape[0]
        )
        virus_data = pd.Series([virus_category, virus_circular, virus_prophage, virus_num_genes, virus_strand_switches,
                                virus_number_amgs, virus_transposase_present, virus_j_present],
                               index=VIRUS_STATS_COLUMNS, name=scaffold)
        # get vogdb categories
        # when vogdb has multiple categories only the first is taken
        gene_counts = Counter([i.split(';')[0] for i in frame.vogdb_categories.replace('', 'Xx')])
        named_gene_counts = {VOGDB_TYPE_NAMES[key]: value for key, value in gene_counts.items()}
        gene_counts_series = pd.Series(named_gene_counts, name=scaffold)
        viral_stats_series.append(virus_data.append(gene_counts_series))
    return pd.DataFrame(viral_stats_series).fillna(0)


def make_viral_distillate(potential_amgs, genome_summary_frame):
    rows = []
    for gene, row in potential_amgs.iterrows():
        gene_ids = get_ids_from_row(row) & set(genome_summary_frame.index)
        if len(gene_ids) > 0:
            for gene_id in gene_ids:
                gene_summary = genome_summary_frame.loc[gene_id]
                if type(gene_summary) is pd.Series:
                    rows.append([gene, row['scaffold'], gene_id, gene_summary['gene_description'],
                                 gene_summary['sheet'], gene_summary['header'], gene_summary['subheader'],
                                 gene_summary['module'], row['auxiliary_score'], row['amg_flags']])
                else:
                    rows.extend(
                        [
                            gene,
                            row['scaffold'],
                            gene_id,
                            sub_gene_summary['gene_description'],
                            sub_gene_summary['sheet'],
                            sub_gene_summary['header'],
                            sub_gene_summary['subheader'],
                            sub_gene_summary['module'],
                            row['auxiliary_score'],
                            row['amg_flags'],
                        ]
                        for sub_gene_id, sub_gene_summary in gene_summary.iterrows()
                    )
        else:
            warnings.warn(f"No distillate information found for gene {gene}")
            rows.append([gene, row['scaffold'], '', '', '', '', '', '', row['auxiliary_score'],
                         row['amg_flags']])
    return pd.DataFrame(rows, columns=VIRAL_DISTILLATE_COLUMNS)


def make_vgf_order(amgs):
    amg_score_dict = {scaffold: ((1/frame['auxiliary_score']).sum(), len(frame))
                      for scaffold, frame in amgs.groupby('scaffold')}
    amg_scores = pd.DataFrame.from_dict(amg_score_dict, columns=['AMG_score', 'AMG_count'],
                                        orient='index')
    return list(amg_scores.sort_values(['AMG_score', 'AMG_count'], ascending=False).index)


def make_amg_count_column(potential_amgs, vgf_order=None):
    # build count column
    amg_counts = pd.DataFrame(Counter(potential_amgs.scaffold).items(), columns=['Contig Name', 'Number'])
    amg_counts['AMG Count'] = 'AMG Count'
    return (
        alt.Chart(
            amg_counts,
            width=HEATMAP_CELL_WIDTH + 10,
            height=HEATMAP_CELL_HEIGHT * len(amg_counts),
        )
        .encode(
            x=alt.X(
                'AMG Count',
                title=None,
                axis=alt.Axis(labelLimit=0, labelAngle=90),
            ),
            y=alt.Y(
                'Contig Name',
                title=None,
                axis=alt.Axis(labelLimit=0),
                sort=vgf_order,
            ),
            text='Number',
        )
        .mark_text()
    )


def make_viral_functional_df(annotations, genome_summary_frame, groupby_column='scaffold'):
    # build dict of ids per genome
    vgf_to_id_dict = defaultdict(defaultdict_list)
    for vgf, frame in annotations.groupby(groupby_column, sort=False):
        for gene, row in frame.iterrows():
            id_list = get_ids_from_row(row)
            for id_ in id_list:
                vgf_to_id_dict[vgf][id_].append(gene)
    # build long from data frame
    rows = []
    for category, category_frame in genome_summary_frame.groupby('sheet'):
        for header, header_frame in category_frame.groupby('module'):
            header_id_set = set(header_frame.index.to_list())
            curr_rows = []
            for vgf, id_dict in vgf_to_id_dict.items():
                present_in_bin = False
                functions_present = []
                amgs_present = []
                for id_, amgs in id_dict.items():
                    if id_ in header_id_set:
                        present_in_bin = True
                        functions_present.append(id_)
                        amgs_present += amgs
                curr_rows.append([category, header, ', '.join(amgs_present), ', '.join(functions_present), vgf,
                                  present_in_bin])
            if sum(i[-1] for i in curr_rows) > 0:
                rows += curr_rows
    return pd.DataFrame(rows, columns=VIRAL_LIQUOR_HEADERS)


def make_viral_functional_heatmap(functional_df, vgf_order=None):
    # build heatmaps
    charts = []
    for group, frame in functional_df.groupby('Category', sort=False):
        # set variables for chart
        function_order = get_ordered_uniques(list(frame['Function']))
        num_vgfs_in_frame = len(set(frame['Contig Name']))
        chart_width = HEATMAP_CELL_WIDTH * len(function_order)
        chart_height = HEATMAP_CELL_HEIGHT * num_vgfs_in_frame
        # set up colors for chart
        rect_colors = alt.Color('Present in Contig',
                                legend=alt.Legend(symbolType='square', values=[True, False]),
                                sort=[True, False],
                                scale=alt.Scale(range=['#e5f5f9', '#2ca25f']))
        # define chart
        # TODO: Figure out how to angle title to take up less space
        c = alt.Chart(frame, title=alt.TitleParams(group)).encode(
            x=alt.X('Function', title=None, axis=alt.Axis(labelLimit=0, labelAngle=90), sort=function_order),
            y=alt.Y('Contig Name', axis=alt.Axis(title=None, labels=False, ticks=False), sort=vgf_order),
            tooltip=[alt.Tooltip('Contig Name'),
                     alt.Tooltip('Category'),
                     alt.Tooltip('Function'),
                     alt.Tooltip('AMG Genes'),
                     alt.Tooltip('Genes Present')]
        ).mark_rect().encode(color=rect_colors).properties(
            width=chart_width,
            height=chart_height)
        charts.append(c)
    return alt.hconcat(*charts, spacing=5)


# def summarize_vgfs(input_file, output_dir, groupby_column='scaffold', max_auxiliary_score=3, remove_transposons=False,
#                    remove_fs=False, remove_js=False, custom_distillate=None):
def summarize_vgfs(input_file, output_dir, groupby_column='scaffold', max_auxiliary_score=3,
                   remove_transposons=False, remove_fs=False, custom_distillate=None):
    start_time = datetime.now()

    # set up
    annotations = pd.read_csv(input_file, sep='\t', index_col=0).fillna('')
    database_handler = DatabaseHandler()
    if database_handler.dram_sheet_locs.get('genome_summary_form') is None:
        raise ValueError('Genome summary form location must be set in order to summarize genomes')
    mkdir(output_dir)
    genome_summary_form = pd.read_csv(database_handler.dram_sheet_locs['genome_summary_form'], sep='\t', index_col=0)
    if custom_distillate is not None:
        custom_distillate_form = pd.read_csv(custom_distillate, sep='\t', index_col=0)
        genome_summary_form = pd.concat([genome_summary_form, custom_distillate_form])
        # add M's from custom distillate
        annotations['amg_flags'] = add_custom_ms(annotations, custom_distillate_form)
    print(
        f'{str(datetime.now() - start_time)}: Retrieved database locations and descriptions'
    )

    # get potential AMGs
    # potential_amgs = filter_to_amgs(annotations.fillna(''), max_aux=max_auxiliary_score,
    #                                 remove_transposons=remove_transposons, remove_fs=remove_fs, remove_js=remove_js)
    potential_amgs = filter_to_amgs(annotations, max_aux=max_auxiliary_score,
                                    remove_transposons=remove_transposons, remove_fs=remove_fs)
    print(f'{str(datetime.now() - start_time)}: Determined potential amgs')

    # make distillate
    viral_genome_stats = make_viral_stats_table(annotations, potential_amgs, groupby_column)
    viral_genome_stats.to_csv(path.join(output_dir, 'vMAG_stats.tsv'), sep='\t')
    print(
        f'{str(datetime.now() - start_time)}: Calculated viral genome statistics'
    )

    viral_distillate = make_viral_distillate(potential_amgs, genome_summary_form)
    viral_distillate.to_csv(path.join(output_dir, 'amg_summary.tsv'), sep='\t', index=None)
    print(f'{str(datetime.now() - start_time)}: Generated AMG summary')

    # make liquor
    vgf_order = make_vgf_order(potential_amgs)
    amg_column = make_amg_count_column(potential_amgs, vgf_order)
    viral_function_df = make_viral_functional_df(potential_amgs, genome_summary_form, groupby_column=groupby_column)
    viral_functional_heatmap = make_viral_functional_heatmap(viral_function_df, vgf_order)
    alt.hconcat(amg_column, viral_functional_heatmap, spacing=5).save(path.join(output_dir, 'product.html'))
    print(f'{str(datetime.now() - start_time)}: Generated product heatmap')
    print(f"{str(datetime.now() - start_time)}: Completed distillation")
