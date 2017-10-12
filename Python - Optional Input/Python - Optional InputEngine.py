import AlteryxPythonSDK as Sdk
import xml.etree.ElementTree as Et


class AyxPlugin:
    """
    Implements the plugin interface methods, to be utilized by the Alteryx engine to communicate with a plugin.
    Prefixed with "pi_", the Alteryx engine will expect the below five interface methods to be defined.

    """

    def __init__(self, n_tool_id: int, alteryx_engine: object, output_anchor_mgr: object):
        """
        Acts as the constructor for AyxPlugin.
        :param n_tool_id: The assigned unique identification for a tool instance.
        :param alteryx_engine: Provides an interface into the Alteryx engine.
        :param output_anchor_mgr: A helper that wraps the outgoing connections for a plugin.
        """

        # Miscellaneous properties
        self.n_tool_id = n_tool_id
        self.name = 'PythonOptionalInput_' + str(self.n_tool_id)
        self.initialized = False
        self.single_input = None

        # Engine handle
        self.alteryx_engine = alteryx_engine

        # Output anchor management
        self.output_anchor_mgr = output_anchor_mgr
        self.output_anchor = None

        # Record management
        self.output_field = None

        # Default config settings
        self.column_name = None
        self.starting_value = None
        self.total_record_count = None
        self.output_type = None
        self.record_increment = None
        self.previous_inc_value = None

    def pi_init(self, str_xml: str):
        """
        Called when the Alteryx engine is ready to provide the tool configuration from the GUI.
        :param str_xml: The raw XML from the GUI.
        """

        # Getting the dataName data property from the Gui.html
        self.column_name = Et.fromstring(str_xml).find('FieldName').text if 'FieldName' in str_xml else None
        self.total_record_count = int(Et.fromstring(str_xml).find('EndValue').text) if 'EndValue' in str_xml else None
        self.record_increment = int(Et.fromstring(str_xml).find('StepByValue').text) if 'StepByValue' in str_xml else None
        self.starting_value = int(Et.fromstring(str_xml).find('StartValue').text) - self.record_increment if 'StartValue' in str_xml else None
        field_type = Et.fromstring(str_xml).find('FieldType').text if 'FieldType' in str_xml else None
        if field_type == 'Int16':
            self.output_type = Sdk.FieldType.int16
        elif field_type == 'Int32':
            self.output_type = Sdk.FieldType.int32
        elif field_type == 'Int64':
            self.output_type = Sdk.FieldType.int64
        elif field_type == 'Double':
            self.output_type = Sdk.FieldType.double

        # Getting the output anchor from Config.xml by the output connection name
        self.output_anchor = self.output_anchor_mgr.get_output_anchor('Output')


    def pi_add_incoming_connection(self, str_type: str, str_name: str) -> object:
        """
        The IncomingInterface objects are instantiated here, one object per incoming connection.
        Called when the Alteryx engine is attempting to add an incoming data connection.
        :param str_type: The name of the input connection anchor, defined in the Config.xml file.
        :param str_name: The name of the wire, defined by the workflow author.
        :return: The IncomingInterface object(s).
        """

        self.single_input = IncomingInterface(self)
        return self.single_input

    def pi_add_outgoing_connection(self, str_name: str) -> bool:
        """
        Called when the Alteryx engine is attempting to add an outgoing data connection.
        :param str_name: The name of the output connection anchor, defined in the Config.xml file.
        :return: True signifies that the connection is accepted.
        """

        return True


    def pi_push_all_records(self, n_record_limit: int) -> bool:
        """
        Called by the Alteryx engine for tools that have no incoming connection connected.
        Only pertinent to tools which have no upstream connections, like the Input tool.
        :param n_record_limit: Set it to <0 for no limit, 0 for no records, and >0 to specify the number of records.
        :return: True for success, False for failure.
        """

        # Checking if column_name is empty. If it is, records will stop processing and result in an error.
        if self.column_name is None:
            self.alteryx_engine.output_message(self.n_tool_id, Sdk.EngineMessageType.error, self.xmsg('Field name cannot be empty. Please enter a field name.'))
            return False

        # Checking if column_name is greater then 255 characters. If it is, records will stop processing and result in an error.
        if len(self.column_name) > 255:
            self.alteryx_engine.output_message(self.n_tool_id, Sdk.EngineMessageType.error, self.xmsg('Field name cannot be greater then 255 characters.'))
            return False

        # Save a reference to the RecordInfo passed into this function in the global namespace, so we can access it later.
        record_info_out = Sdk.RecordInfo(self.alteryx_engine)

        # Adds the new field to the record.
        self.output_field = record_info_out.add_field(self.column_name, self.output_type)

        # Lets the downstream tools know what the outgoing record metadata will look like, based on record_info_out.
        self.output_anchor.init(record_info_out)

        # Creating a new, empty record creator based on record_info_out's record layout.
        record_creator = record_info_out.construct_record_creator()

        self.previous_inc_value = self.starting_value

        # Create new column and increments the value by self.record_increment.
        for i in range(0, self.total_record_count):

            loop_value = self.previous_inc_value + self.record_increment

            # Set the value on our new column in the record_creator helper to be the new record_count.
            record_info_out[0].set_from_int64(record_creator, loop_value)

            # Pass the record downstream.
            out_record = record_creator.finalize_record()

            # Pushes record to output connection, passing False means completed connections will be automatically closed.
            self.output_anchor.push_record(out_record, False)

            # Sets the capacity in bytes for variable-length data in this record to 0.
            record_creator.reset(0)

            self.previous_inc_value = loop_value
            
        # Make sure that the output anchor is closed.
        self.output_anchor.close()

        return True

    def pi_close(self, b_has_errors: bool):
        """
        Called after all records have been processed..
        :param b_has_errors: Set to true to not do the final processing.
        """

        # Checks whether connections were properly closed.
        self.output_anchor.assert_close()

    def xmsg(self, msg_string: str):
        """
        A non-interface, non-operational placeholder for the eventual localization of predefined user-facing strings.
        :param msg_string: The user-facing string.
        :return: msg_string
        """

        return msg_string

class IncomingInterface:
    """
    This class is returned by pi_add_incoming_connection, and it implements the incoming interface methods, to be
    utilized by the Alteryx engine to communicate with a plugin when processing an incoming connection.
    Prefixed with "ii_", the Alteryx engine will expect the below four interface methods to be defined.
    """

    def __init__(self, parent: object):
        """
        Acts as the constructor for IncomingInterface. Instance variable initializations should happen here for PEP8 compliance.
        :param parent: AyxPlugin
        """

        # Miscellaneous properties
        self.parent = parent

        # Record management
        self.record_copier = None
        self.record_creator = None

    def ii_init(self, record_info_in: object) -> bool:
        """
        Called when the incoming connection's record metadata is available or has changed, and
        has let the Alteryx engine know what its output will look like.
        :param record_info_in: A RecordInfo object for the incoming connection's fields.
        :return: True for success, otherwise False.
        """

        # Checking if column_name is empty. If it is, records will stop processing and result in an error.
        if self.parent.column_name is None:
            self.parent.alteryx_engine.output_message(self.parent.n_tool_id, Sdk.EngineMessageType.error, self.parent.xmsg('Field name cannot be empty. Please enter a field name.'))
            return False

        # Checking if column_name is greater then 255 characters. If it is, records will stop processing and result in an error.
        if len(self.parent.column_name) > 255:
            self.parent.alteryx_engine.output_message(self.parent.n_tool_id, Sdk.EngineMessageType.error, self.parent.xmsg('Field name cannot be greater then 255 characters.'))
            return False

        # Returns a new, empty RecordCreator object that is identical to record_info_in.
        record_info_out = record_info_in.clone()

        # Adds field to record with specified name and output type.
        record_info_out.add_field(self.parent.column_name, self.parent.output_type)

        # Lets the downstream tools know what the outgoing record metadata will look like, based on record_info_out.
        self.parent.output_anchor.init(record_info_out)

        # Creating a new, empty record creator based on record_info_out's record layout.
        self.record_creator = record_info_out.construct_record_creator()

        # Instantiate a new instance of the RecordCopier class.
        self.record_copier = Sdk.RecordCopier(record_info_out, record_info_in)

        # Map each column of the input to where we want in the output.
        for index in range(record_info_in.num_fields):

            # Adding a field index mapping.
            self.record_copier.add(index, index)

        # Let record copier know that all field mappings have been added.
        self.record_copier.done_adding()

        # Grab the index of our new field in the record, so we don't have to do a string lookup on every push_record.
        self.parent.output_field = record_info_out[record_info_out.get_field_num(self.parent.column_name)]
        return True

    def ii_push_record(self, in_record: object) -> bool:
        """
        Responsible for pushing records out, under a count limit set by the user in n_record_select.
        Called when an input record is being sent to the plugin.
        :param in_record: The data for the incoming record.
        :return: True for success, otherwise False.
        """

        # Increment our custom starting_value variable by the selected record increment to show we have a new record.
        self.parent.starting_value += self.parent.record_increment

        # Copy the data from the incoming record into the outgoing record.
        self.record_creator.reset()
        self.record_copier.copy(self.record_creator, in_record)

        # Sets the value of this field in the specified record_creator from an int64 value.
        self.parent.output_field.set_from_int64(self.record_creator, self.parent.starting_value)

        out_record = self.record_creator.finalize_record()

        # Push the record downstream and quit if there's a downstream error.
        if not self.parent.output_anchor.push_record(out_record):
            return False

        return True

    def ii_update_progress(self, d_percent: float):
        """
        Called when by the upstream tool to report what percentage of records have been pushed.
        :param d_percent: Value between 0.0 and 1.0.
        """

        # Inform the Alteryx engine of the tool's progress.
        self.parent.alteryx_engine.output_tool_progress(self.parent.n_tool_id, d_percent)

        # Inform the outgoing connections of the tool's progress.
        self.parent.output_anchor.update_progress(d_percent)

    def ii_close(self):
        """
        Called when the incoming connection has finished passing all of its records.
        """

        # Close outgoing connections.
        self.parent.output_anchor.close()