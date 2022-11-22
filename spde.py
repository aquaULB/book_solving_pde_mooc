import re
import os
import hashlib
import glob

class SpdeContent():
    """Class representing the book.
    It should be populated by reading the
    content of the Jupyter Book _toc.yml file
    """

    def __init__(self, toc_file):

        # set toc file
        self.toc_file = toc_file
        self.files = None

    def file_list(self):
        """ Read a _toc.yml and stores
        all md filenames in a list
        """
        files = []
        reg_file = re.compile(r'(?<=file: )\S+')

        with open(self.toc_file, "r") as f:
            lines = f.readlines()

        for line in lines:
            filepath = re.search(reg_file, line)
            if filepath:
                files.append(SpdeFile(filepath[0] + '.md'))

        self.files = files

    def parse_files(self):
        """
        Perform some operations on each
        file in the book table of content
        """

        for file in self.files:
            print(f'Processing {file.name}...')
            file.read()
            file.remove_block('<div class=\"copyright\"', '</div>')
            file.remove_block(r'\+\+\+ {\"toc\": true}', r'\+\+\+')
            file.remove_block(r'^css_file', r'^HTML\(open\(', 2, 1)
            file.amsmath_envs_to_directives()
            found = file.latex_to_myst_roles()
            if found:
                file.html_to_myst_ref_section()
            file.remove_trailing_line()
            file.save()

        print('Parsing finished')

    def merge_bibtex_files(self):
        """
        Merge all bibtex files in a single file
        and eliminate duplicate entries
        """

        bib_files = glob.glob('solving_pde_mooc/**/*.bib', recursive = True)
        # print(bib_files)

        lines_merged = []

        for file in bib_files:
            with open(file, "r") as f:
                lines = f.readlines()
            lines_merged.extend(lines)            
            f.close()
        
        with open('./references.bib', "w") as f:
            for line in lines_merged:
                f.write(str(line))
        f.close()
        #print(lines_merged)


class SpdeFile():
    """ Class to manipulate the content
    of myst markdown files
    """

    def __init__(self, path):

        self.path = path
        self.lines = None
        self.name = os.path.basename(self.path)
        self.hash = hashlib.sha256(
                str(self.path).encode('utf-8')
            ).hexdigest()[-6:]

    def read(self):
        """ Open and store file content as a list
        in the lines instance variable
        """

        with open(self.path, "r") as f:
            self.lines = f.readlines()
        f.close()

    def save(self, freeup=True):
        """ Saves the list contained in the lines
        instance variable to the corresponding file.

        Parameter
        ---------
        freeup : bool (optional)
            By default, the list containing the saved lines
            is freed after saving.
        """

        with open(self.path, "w") as f:
            f.writelines(self.lines)
        f.close()

        # Release memory
        if freeup:
            self.lines = None

    def remove_block(self, start, end, k=0, m=0):
        """Removes a block of consecutive lines in
        a list of lines

        Parameters
        ----------
        start : string
            string indicating the beginning of the
            block to remove. Will be compiled into
            a regex.
        stop : string
            string indicating the end of the
            block to remove. Will be compiled into
            a regex.
        k : integer (optional)
            number of extra lines to remove before start
        l : integer (optional)
            number of extra lines to remove after end.
        """

        s_found = False
        e_found = False

        s_reg = re.compile(start)
        e_reg = re.compile(end)

        for i, line in enumerate(self.lines):
            # Identify beginning of block
            if re.search(s_reg, line):
                s_index = i
                s_found = True
                continue
            # Identify end of block if beginning found
            if re.search(e_reg, line) and s_found:
                e_index = i+1
                e_found = True
                break

        if s_found and e_found:
            del self.lines[s_index-k:e_index+m]

    def remove_trailing_line(self):
        """ Removes trailing blank lines
        This required by myst parser
        """

        while self.lines[-1] == "\n":
            del self.lines[-1]

    def amsmath_envs_to_directives(self):
        """ Replace amsmath environments with myst directives
        Environments considered:
            \begin{align} ... \end{align}
            \begin{equation} ... \end{equation}
            $$ ... $$

        If an environment contains a \label{eqlabel}, it has
        to be on the line following its opening

        All environments are converted to this myst directive:

            ```math
            :label: eqlabel
            ...
            ```
        """

        in_env = False

        # To search for optional label.
        reg_label = re.compile(r'\\label{(.*?)}')

        begin_envs = [r'\begin{equation}', r'\begin{align}',
                        r'\begin{equation*}', r'\begin{align*}', r'$$']
        end_envs = [r'\end{equation}', r'\end{align}',
                        r'\end{equation*}', r'\end{align*}', r'$$']

        for i, line in enumerate(self.lines):

            # Locate environment beginning
            if not in_env:
                if line.strip("\n") in begin_envs:  # start env
                    in_env = True
                    self.lines[i] = '```{math}\n'
                    continue

            # Steps if environment beginning found
            else:
                label = re.search(reg_label, line)
                if label:
                    self.lines[i] = ':label: ' + label.group(1) + '\n'
                if line.strip("\n") in end_envs:  # end env
                    self.lines[i] = '```\n'
                    in_env = False

    def latex_to_myst_roles(self):
        """ Method to replace certain latex commands with myst
        roles. The objective is to allow classic \ref, \eqref and
        \cite commands in the notebooks.
        """

        # Patterns for equation references
        ref_types = ['ref', 'eqref']

        # Pattern(s) for citations
        cite_types = ['cite']

        # Collect all patterns
        all_types = ref_types + cite_types

        # Regex to match latex commands \..{..}
        reg_command = re.compile(r'\$?\\\S+?{.+?}\$?')

        # Regex to determine which latex command
        reg_command_type = re.compile(r'\\(.*?){')

        # Regex to determine key inside brackets
        reg_key = re.compile(r'{(.*?)}')

        # True if at least one \cite{} found; we then
        # to add a myst directive to compile bibtex file
        found = False

        for i, line in enumerate(self.lines):
            # Find latex commands
            commands = re.findall(reg_command, line)
            for command in commands:
                # Identify type of command
                command_type = re.search(reg_command_type, command)
                if command_type.group(1) in all_types:
                    # Perform actions if we have a command type
                    # that needs to be converted to myst
                    key = re.search(reg_key, command)
                    if command_type.group(1) in ref_types:
                        # Equation references
                        myst_role = '{eq}`' + key.group(1) + '`'
                    elif command_type.group(1) in cite_types:
                        # Citations
                        myst_role = '{footcite}`' + key.group(1) + '`'
                        found = True
                    self.lines[i] = self.lines[i].replace(command, myst_role)

        return found

    def html_to_myst_ref_section(self):
        """ Method to add a myst directive to compile the bibtex
        file if citations have been found. It is assumed that the
        original reference section is now located at the very end
        of the file.
        """

        directive = [
                        '```{footbibliography}\n',
                        '```',
                    ]

        for i, line in enumerate(self.lines):
            if line.strip("\n") == "## References":
                self.lines = self.lines[:i+1]
                break

        self.lines.extend(directive)


# Create book and create file list from toc
book = SpdeContent('_toc.yml')
book.file_list()

# Parse all files
book.parse_files()

# Merge bibtex files
book.merge_bibtex_files()
