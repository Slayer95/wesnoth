#[=======================================================================[.rst:
FindTranslationTools
--------------------

Find the tools needed for updating the potfiles and translations.

Result Variables
^^^^^^^^^^^^^^^^

This module defines the following variables:

	GETTEXT_MSGINIT_EXECUTABLE
	GETTEXT_XGETTEXT_EXECUTABLE
	GETTEXT_MSGCAT_EXECUTABLE
	GETTEXT_MSGATTRIB_EXECUTABLE
	ASCIIDOC_EXECUTABLE
	DOS2UNIX_EXECUTABLE
	PO4A-TRANSLATE_EXECUTABLE
	PO4A-UPDATEPO_EXECUTABLE
	XSLTPROC_EXECUTABLE

#]=======================================================================]

set(TRANSLATION_TOOLS_FOUND true)

# Try to find the given EXECUTABLE_NAME and set FIND_VARIABLE to its location
# Sets TRANSLATION_TOOLS_FOUND to false if it can't find the required exe
macro(_find_translation_tool FIND_VARIABLE EXECUTABLE_NAME)
	find_program(${FIND_VARIABLE} ${EXECUTABLE_NAME})
	if(NOT ${FIND_VARIABLE})
		message("${EXECUTABLE_NAME} not found!")
		set(TRANSLATION_TOOLS_FOUND false)
	endif()
endmacro()

_find_translation_tool(GETTEXT_MSGINIT_EXECUTABLE msginit)

_find_translation_tool(GETTEXT_XGETTEXT_EXECUTABLE xgettext)
set(GETTEXT_XGETTEXT_OPTIONS
	--force-po
	--add-comments=TRANSLATORS
	--copyright-holder=\"Wesnoth development team\"
	--msgid-bugs-address=\"https://bugs.wesnoth.org/\"
	--from-code=UTF-8
	--sort-by-file
	--keyword=_
	--keyword=N_
	--keyword=sgettext
	--keyword=vgettext
	--keyword=VGETTEXT
	--keyword=_n:1,2
	--keyword=N_n:1,2
	--keyword=sngettext:1,2
	--keyword=vngettext:1,2
	--keyword=VNGETTEXT:1,2
)

_find_translation_tool(GETTEXT_MSGCAT_EXECUTABLE msgcat)

_find_translation_tool(GETTEXT_MSGATTRIB_EXECUTABLE msgattrib)

_find_translation_tool(DOS2UNIX_EXECUTABLE dos2unix)

if(NOT TRANSLATION_TOOLS_FOUND AND TranslationTools_FIND_REQUIRED)
	message(FATAL_ERROR "Some required translation tools are not found!")
endif()
