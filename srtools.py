import re
import sys
import itertools
import random


COMPLEMENT = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A', 'N': 'N'}


class UnmappedReadError(ValueError):
    """The exception raised when attempting an illegal operation on an unmapped
    read. A consensus sequence cannot be derived from an unmapped read, for
    example.

    """
    pass


class NullSequenceError(ValueError):
    """The exception raised when attempting to illegally manipulate a null
    sequence (i.e., an empty sequence or one composed entirely of N's).
    The GC content of a null sequence is undefined, for example.

    """
    pass


class Read():
    """A sam-format sequence read."""

    def __init__(self, qname, flag, rname, pos, mapq, cigar, rnext, pnext,
                 tlen, seq, qual, tags=[]):
        self.qname = str(qname)
        self.flag = int(flag)
        self.rname = str(rname)
        self.pos = int(pos)
        self.mapq = int(mapq)
        self.cigar = read_cigar(cigar)
        self.rnext = str(rnext)
        self.pnext = int(pnext)
        self.tlen = int(tlen)
        self.seq = str(seq)
        self.qual = str(qual)
        self.tags = [str(x) for x in tags]

    def __eq__(self, other):
        tests = [self.qname == other.qname,
                 self.flag == other.flag,
                 self.rname == other.rname,
                 self.pos == other.pos,
                 self.mapq == other.mapq,
                 self.cigar == other.cigar,
                 self.rnext == other.rnext,
                 self.pnext == other.pnext,
                 self.tlen == other.tlen,
                 self.seq == other.seq,
                 self.qual == other.qual,
                 self.tags == other.tags]

        return all(result == True for result in tests)

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        attrs = [self.qname, self.flag, self.rname, self.pos, self.mapq,
                 print_cigar(self.cigar), self.rnext, self.pnext,
                 self.tlen, self.seq, self.qual] + self.tags
        return "\t".join([str(x) for x in attrs])

    def get_covered_range(self):
        """Returns a tuple consisiting of the first and last position covered
        by the read.

        """
        first_base = self.pos
        last_base = self.pos + sum([i for i, o in self.cigar if o == "M"]) - 1
        return (first_base, last_base)


class ReadStream(object):
    """A stream of reads from a sam file."""
    def __init__(self, sam_file):
        self.sam_file = sam_file
        self.stream = self.read_generator()

    def read_generator(self):
        with open(self.sam_file) as f:
            for line in f:
                if line and not line.startswith("@"):
                    yield parse_sam_read(line)

    def __next__(self):
        return next(self.stream)

    def __iter__(self):
        return self

    def rewind(self):
        """Calls the read_generator method, thereby reseting the stream of
        reads.

        """
        self.stream = self.read_generator()


class Alignment():
    """A sam-format sequence alignment"""
    def __init__(self, head, reads):
        self.head = head
        self.reads = reads

    def __str__(self):
        headstr = self.head
        readstr = "\n".join([str(read) for read in self.reads])
        return headstr + readstr

    def __iter__(self):
        return self.reads

    def __next__(self):
        return next(self.reads)

    def filter_reads(self, function):
        """Returns a generator of reads where function(read) returns a truthy 
        value.

        """
        for r in self.reads:
            if function(r):
                yield r

    def filter_consecutive_reads(self, function):
        """Returns a generator of consecutive reads where function(read)
        returns a truthy value. Helper method fo Alignment.collect_reads.

        """
        reads = self.reads
        first_read = next(reads)
        test_value = function(first_read)
        yield first_read
        for read in self.reads:
            if function(read) == test_value:
                yield read

    def collect_reads(self, function):
        """Returns a generator which yields generators of consecutive reads 
        which all return the same value when the specified function is applied.

        """
        while True:
            yield self.filter_consecutive_reads(function)


class Feature():
    """A GFF genomic feature."""
    def __init__(self, sequence, source, f_type, start, end, score,
                 strand, frame, attribute):
        self.sequence = str(sequence)
        self.source = str(source)
        self.f_type = str(f_type)
        self.start = int(start)
        self.end = int(end)
        self.score = score
        self.strand = strand
        self.frame = frame
        self.attribute = attribute


class GenomeAnnotation():
    """A genome-spanning collection of Features"""
    def __init__(self, head, features):
        self.head = head
        self.features = features

    def filter_features(self, function):
        """Returns a list of features where function(feature) reutrns a truthy
        value.

        """
        return [f for f in self.features if function(f)]

    def collect_features(self, function):
        """Returns a generator which yields lists of consecutive features which
        all return the same value when the specified function is applied.

        """
        collection = [self.features[0]]
        for feature in self.features[1:]:
            if function(feature) == function(collection[-1]):
                collection.append(feature)
            else:
                yield collection
                collection = [feature]
        yield collection



def read_cigar(cigar):
    """Takes a cigar string, and returns a list of 2-tuples consisting
    of the index (int) and the operation (one-character str).

    """
    return [(int(a), b) for (a, b) in re.findall(r'(\d+)(\D)', cigar)]

def print_cigar(cigar):
    """Prints a cigar in the standard SAM format"""
    if not cigar:
        cigar_str = '*'
    else:
        cigar_str =\
               ''.join([str(char) for substr in cigar for char in substr])
               # Strings and flattens the list of tuples
    return cigar_str


def reverse_complement(sequence):
    rc = []
    seq = list(sequence)
    while seq:
        rc.append(COMPLEMENT[seq.pop()])
    return "".join(rc)


def parse_sam_read(string):
    """Takes a string in SAMfile format and returns a Read object."""
    fields = string.strip().split()
    return Read(fields[0], fields[1], fields[2], fields[3], fields[4],
                fields[5], fields[6], fields[7], fields[8], fields[9],
                fields[10], tags=fields[11:])


def get_head(samfile):
    """Returns the head of a sam_file"""
    headlines = []
    with open(samfile) as f:
        for line in f:
            if line and line.startswith("@"):
                headlines.append(line)
            else:
                return "".join(headlines)
    

def read_sam(samfile):
    """Creates an Alignment object from a correctly formatted SAM file.
    
    Note: the Alignment.reads object is a generator expression. This (hopefully)
    reduces space complexity to the point where it's possible to actually read
    a real SAM file (which can easily be 50 Gb) in reasonable memory, but there
    is no backtracking. Once you've read a read, it gets garbage collected.

    """
    head = get_head(samfile)
    reads = ReadStream(samfile)
    return Alignment(head=head, reads=reads)


def read_fasta(fasta_file):
    """Returns a dictionary a sequence names and values from a fasta-format file."""
    seq_dict = {}
    with open(fasta_file) as f:
        for line in f:
            if line.startswith(">"):
                name = line[1:].strip()
            elif line.strip():
                seq_dict.setdefault(name, "")
                seq_dict[name] += line.strip()
    return seq_dict


def parse_gff_feature(feature_string):
    """Creates a Feature object from a GFF feature string."""
    fields = feature_string.strip().split("\t")

    while True:
        try:
            fields[fields.index('.')] = None
        except ValueError:
            break

    sequence = fields[0]
    source = fields[1]
    f_type = fields[2]
    start = int(fields[3])
    end = int(fields[4])
    if fields[5]:
        score = float(fields[5])
    else:
        score = fields[5]
    strand = fields[6]
    frame = fields[7]
    attribute = fields[8]

    return Feature(sequence, source, f_type, start, end, score, strand, 
                   frame, attribute)


def read_gff(gff_file):
    """Creates a GenomeAnnotation object from a GFF file"""
    headlines = []
    features = []
    with open(gff_file) as f:
        for line in f:
            if line.startswith("##"):
                headlines.append(line)
            elif line.startswith("#"):
                pass
            else:
                features.append(parse_gff_feature(line))
    return GenomeAnnotation(head="".join(headlines), features=features)



def convert_indecies(cigar):
    """Converts a cigar from (n, operator) format to (index, n, operator).
    The index is the zero-based position of the operator, and n is its length.

    """
    index = 0
    converted_cigar = []
    for i, o in cigar:
        converted_cigar.append((index, i, o))
        index += i
    return converted_cigar


def make_dot_queue(stripped_read, stripped_read_list):
    """Returns a queue of positions at which the stripped_read should be dotted
    to indicate an indel. A stripped_read is a 3-tuple of the sequence, the
    cigar and the position. Helper function for dot_indels.

    """
    queue = []
    s_seq, s_cigar, s_pos = stripped_read
    for read in stripped_read_list:
        seq, cigar, pos = read
        c_cigar = convert_indecies(cigar)
        offset = pos - s_pos
        if seq == s_seq and pos == s_pos:
            queue.extend([(i, n) for i, n, o in c_cigar if o in "ND"])
        else:
            queue.extend([(i + offset, n) for i, n, o in c_cigar if o == "I"])
    return queue


def dot_from_queue(stripped_read, queue):
    """Returns a short-read sequence with dots indicating the positions of
    indels. A stripped_read is a 3-tuple of the sequence, the cigar and the
    position.Helper function for dot_indels.

    """
    seq, cigar, pos = stripped_read
    for i, n in queue:
        seq = seq[:i] + ('.' * n) + seq[i:]
    return seq


def dot_indels(reads):
    """Given an iterable of reads, adds dots to the sequences where there are
    indels. Returns a list of 3-tuples of the dotted sequence, the cigar and
    the position.

    """
    stripped_reads = [(read.seq, read.cigar, read.pos) for read in reads]
    dotted_reads = []
    for sr in stripped_reads:
        queue = make_dot_queue(sr, stripped_reads)
        normalized_read = dot_from_queue(sr, queue)
        dotted_reads.append(normalized_read)

    cigars = [c for s, c, p in stripped_reads]
    positions = [p for s, c, p in stripped_reads]
    return zip(dotted_reads, cigars, positions)


def majority(nucleotides, cutoff=0.5):
    """Given a collection of strings, returns the majority rule consensus among
    them. If there is no majority above the cutoff fraction, returns "N".

    """
    for i in nucleotides:
        if nucleotides.count(i) / len(nucleotides) > cutoff:
            consensus = i
            break
    else:
        consensus = "N"
    return consensus

    
def consensus(reads, cutoff=0.5):
    """Returns the consensus sequence of a collection of reads."""
    all_nucleotides = {}
    for read in dot_indels(reads):
        seq, cigar, pos = read
        if pos == 0:
            raise UnmappedReadError
        else:
            index = pos
            for nuc in seq:
                all_nucleotides.setdefault(index, [])
                all_nucleotides[index].append(nuc)
                index += 1

    consensus_sequence = []
    for position in range(min(all_nucleotides), max(all_nucleotides) + 1):
        try:
            n = majority(all_nucleotides[position], cutoff=cutoff)
            consensus_sequence.append(n)
        except KeyError:
            consensus_sequence.append("N")
    consensus = "".join(consensus_sequence)
    return consensus.replace('.', '')


def overlaps(read1, read2):
    """Returns True if the two reads cover at least one base in common and
    False otherwise.

    """
    x0, x1 = read1.get_covered_range()
    y0, y1 = read2.get_covered_range()

    return x0 <= y0 <= x1 or y0 <= y1 <= x1


def expressed_loci(reads):
    """Returns a generator object which yields lists of overlapping reads"""
    locus = []
    for read in reads:
        if not locus or overlaps(locus[-1], read):
            locus.append(read)
        else:
            yield locus
            locus = [read]
    yield locus


def coverage(reads):
    """Returns a tuple consisting of the positions of the first and last base
    covered by the list of reads.

    """
    if not reads:
        return (0,0)

    first, last = reads[0].get_covered_range() 
    for read in reads[1:]:
        x0, x1 = read.get_covered_range()
        if x0 < first:
            first = x0
        if x1 > last:
            last = x1
    return (first, last)


def in_features(reads, features):
    """Returns a boolean indicating whether any of the reads in the first
    argument overlap with any of the features in the second.

    """
    overlap = False
    r0, r1 = coverage(reads)
    for f in features:
        if f.start <= r0 <= f.end or f.start <= r1 <= f.end:
            overlap = True
            break
        elif f.start > r1:
            break
    return overlap


def gc_content(sequence):
    """Returns the fraction of the sequence which consists of GC base pairs.

    """
    base_counts = {x: sequence.count(x) for x in sequence if x in "ACGT"}
    base_counts.setdefault("G", 0)
    base_counts.setdefault("C", 0)
    total = sum(base_counts.values())

    if total == 0:
        raise NullSequenceError

    gc_count = base_counts["G"] + base_counts["C"]
    return gc_count / total


def block_sequence(seq, start, n):
    """Splits a sequence into blocks of size n, prepended by the first 'start' items.
    Helper function for reading_frames.

    """
    blocks = [] 
    if start != 0:
        blocks.append(seq[:start])
    blocks.extend([seq[i:i+n] for i in range(start, len(seq), n)])
    return  blocks


def reading_frames(sequence):
    """Returns the six possible reading frames of the sequence."""

    frames = []

    for i in range(3):
        frames.append(block_sequence(sequence, i, 3))
        frames.append(block_sequence(reverse_complement(sequence), i, 3))

    return frames


def open_reading_frames(sequence):
    """Returns a list of the ORFs of the sequence in all six translation frames."""
    stop_codons = ["TAG", "TAA", "TGA"]
    orfs = []
    for frame in reading_frames(sequence):
        starts = [i for i, x in enumerate(frame) if x == "ATG"]
        stops = [i for i, x in enumerate(frame) if x in stop_codons]
        product = itertools.product(starts, stops)
        fr_list = ["".join(frame[a:b]) for a, b in product if a < b]
        orfs.extend(fr_list)
    return orfs


def random_sequence(length):
    """Returns a random nucleotide sequence of the specified length."""
    return "".join([random.choice("ACGT") for i in range(length)])


def randomize_sequence(seq):
    """Randomizes a sequence of nucleotides, preserving N's"""
    nucs = []
    for nucleotide in seq:
        if nucleotide == "N":
            nucs.append("N")
        else:
            nucs.append(random.choice("ACGT"))
    return "".join(nucs)
